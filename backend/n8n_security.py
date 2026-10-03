"""Short-lived, tenant-scoped read-only capabilities for n8n tool calls."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

TOOL_TOKEN_LIFETIME_SECONDS = 300


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_tool_access_token(tenant_id: int, secret: str) -> str:
    issued_at = int(time.time())
    payload = _b64encode(
        json.dumps(
            {
                "tenant_id": tenant_id,
                "issued_at": issued_at,
                "expires_at": issued_at + TOOL_TOKEN_LIFETIME_SECONDS,
                "scope": "pharmacy.read",
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    signature = hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest()
    return f"{payload}.{_b64encode(signature)}"


def verify_tool_access_token(token: str, secret: str) -> int:
    try:
        payload_part, signature_part = token.split(".", maxsplit=1)
        expected_signature = hmac.new(
            secret.encode("utf-8"), payload_part.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected_signature, _b64decode(signature_part)):
            raise ValueError("Invalid capability.")
        payload = json.loads(_b64decode(payload_part))
        tenant_id = payload.get("tenant_id")
        issued_at = payload.get("issued_at")
        expires_at = payload.get("expires_at")
        now = int(time.time())
        if (
            payload.get("scope") != "pharmacy.read"
            or type(tenant_id) is not int
            or type(issued_at) is not int
            or type(expires_at) is not int
            or issued_at > now + 30
            or expires_at <= now
            or expires_at - issued_at > TOOL_TOKEN_LIFETIME_SECONDS
        ):
            raise ValueError("Invalid or expired capability.")
        return tenant_id
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid or expired capability.") from exc
