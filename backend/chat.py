from collections import defaultdict, deque
from threading import Lock
from time import monotonic
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from backend.auth import get_current_user
from backend.chat_schemas import ChatRequest, ChatResponse
from backend.llm.gemini_service import (
    ChatNotConfiguredError,
    ChatProviderError,
    ChatRateLimitError,
    GeminiChatService,
)
from backend.models import User

router = APIRouter(prefix="/chat", tags=["AI chat"])
CurrentUser = Annotated[User, Depends(get_current_user)]

_service = GeminiChatService()
_RATE_LIMIT = 10
_RATE_WINDOW_SECONDS = 60
_REQUESTS_BY_USER: dict[int, deque[float]] = defaultdict(deque)
_RATE_LOCK = Lock()


def _check_rate_limit(user_id: int) -> None:
    now = monotonic()
    cutoff = now - _RATE_WINDOW_SECONDS
    with _RATE_LOCK:
        requests = _REQUESTS_BY_USER[user_id]
        while requests and requests[0] <= cutoff:
            requests.popleft()
        if len(requests) >= _RATE_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="You have sent several questions. Wait a minute, then try again.",
                headers={"Retry-After": str(_RATE_WINDOW_SECONDS)},
            )
        requests.append(now)


@router.post("/messages", response_model=ChatResponse)
def send_chat_message(payload: ChatRequest, user: CurrentUser) -> ChatResponse:
    _check_rate_limit(user.id)
    try:
        answer = _service.reply(payload.message, payload.history)
    except ChatNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ChatRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
            headers={"Retry-After": "60"},
        ) from exc
    except ChatProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    return ChatResponse(answer=answer)
