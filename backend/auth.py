from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.auth_schemas import AuthResponse, LoginRequest, SignUpRequest
from backend.config import get_settings
from backend.database import get_db
from backend.models import Pharmacy, User, UserSession, utc_now

router = APIRouter(prefix="/auth", tags=["Account"])
DbSession = Annotated[Session, Depends(get_db)]
SESSION_COOKIE = "pharmacy_session"
SESSION_LIFETIME = timedelta(days=14)
SCRYPT_N = 1 << 15
SCRYPT_R = 8
SCRYPT_P = 1


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=32,
        maxmem=64 * 1024 * 1024,
    )
    salt_text = base64.urlsafe_b64encode(salt).decode("ascii")
    digest_text = base64.urlsafe_b64encode(digest).decode("ascii")
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt_text}${digest_text}"


def _verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, n, r, p, salt_text, digest_text = encoded_hash.split("$")
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
            maxmem=64 * 1024 * 1024,
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, MemoryError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def _create_session(db: Session, user: User, response: Response) -> None:
    token = secrets.token_urlsafe(32)
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=_token_hash(token),
            expires_at=utc_now() + SESSION_LIFETIME,
        )
    )
    _set_session_cookie(response, token)


def _auth_response(user: User, pharmacy_name: str | None = None) -> AuthResponse:
    return AuthResponse(
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        pharmacy_id=user.pharmacy_id,
        pharmacy_name=pharmacy_name or user.pharmacy.name,
    )


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sign in to access your pharmacy workspace.",
        headers={"WWW-Authenticate": "Cookie"},
    )


def get_current_user(
    request: Request,
    db: DbSession,
) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise _unauthorized()

    statement = (
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(UserSession.token_hash == _token_hash(token), User.is_active.is_(True))
    )
    row = db.execute(statement).first()
    if row is None:
        raise _unauthorized()

    user_session, user = row
    expires_at = user_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        db.delete(user_session)
        db.commit()
        raise _unauthorized()

    db.info["tenant_id"] = user.pharmacy_id
    return user


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def sign_up(payload: SignUpRequest, response: Response, db: DbSession) -> AuthResponse:
    pharmacy = Pharmacy(name=payload.pharmacy_name)
    user = User(
        pharmacy=pharmacy,
        full_name=payload.full_name,
        email=payload.email,
        password_hash=_hash_password(payload.password),
    )
    db.add(user)
    try:
        db.flush()
        _create_session(db, user, response)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account already exists for this email address.",
        ) from exc
    return _auth_response(user, pharmacy.name)


@router.post("/login", response_model=AuthResponse)
def log_in(payload: LoginRequest, response: Response, db: DbSession) -> AuthResponse:
    user = db.scalar(select(User).where(User.email == payload.email))
    # Run the same password work for unknown email addresses to limit account discovery.
    valid_password = _verify_password(
        payload.password,
        user.password_hash if user is not None else _DUMMY_PASSWORD_HASH,
    )
    if user is None or not user.is_active or not valid_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect.",
        )

    _create_session(db, user, response)
    db.commit()
    return _auth_response(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def log_out(request: Request, response: Response, db: DbSession) -> Response:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        session_record = db.scalar(
            select(UserSession).where(UserSession.token_hash == _token_hash(token))
        )
        if session_record is not None:
            db.delete(session_record)
            db.commit()
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="lax",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=AuthResponse)
def current_account(user: Annotated[User, Depends(get_current_user)]) -> AuthResponse:
    return _auth_response(user)


_DUMMY_PASSWORD_HASH = _hash_password("not-a-real-pharmacy-password")
