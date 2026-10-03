"""Chat provider adapter for an n8n AI Agent webhook."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx

from backend.chat_schemas import ChatHistoryMessage
from backend.config import Settings, get_settings
from backend.llm.gemini_service import ChatNotConfiguredError, ChatProviderError
from backend.n8n_security import issue_tool_access_token


class N8NChatService:
    """Forward app chat turns to n8n and normalize its response."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def reply(
        self,
        message: str,
        history: Sequence[ChatHistoryMessage],
        tenant_id: int,
    ) -> str:
        url = self._settings.n8n_chat_webhook_url
        secret_value = self._settings.n8n_chat_webhook_token
        secret = secret_value.get_secret_value().strip() if secret_value else ""
        if not url or not secret:
            raise ChatNotConfiguredError(
                "n8n chat is selected but not configured. Set N8N_CHAT_WEBHOOK_URL and N8N_CHAT_WEBHOOK_TOKEN on the server."
            )

        payload = {
            "event": "pharmacy.chat.message",
            "message": message,
            "history": [item.model_dump() for item in history],
            "pharmacy_id": tenant_id,
            "tool_access_token": issue_tool_access_token(tenant_id, secret),
        }
        try:
            response = httpx.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {secret}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(90.0, connect=10.0),
                follow_redirects=False,
            )
            response.raise_for_status()
            if len(response.content) > 1_000_000:
                raise ChatProviderError("The n8n workflow returned an oversized response.")
            body: Any = response.json()
        except ChatProviderError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise ChatProviderError(
                "The n8n workflow could not answer right now. Check its webhook and try again."
            ) from exc

        answer = self._extract_answer(body)
        if not answer:
            raise ChatProviderError(
                "The n8n workflow returned no chat answer. Configure it to return an output field."
            )
        return answer

    @staticmethod
    def _extract_answer(body: Any) -> str:
        if isinstance(body, str):
            return body.strip()
        if not isinstance(body, dict):
            return ""
        for key in ("output", "answer", "text", "response"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, dict):
                nested = N8NChatService._extract_answer(value)
                if nested:
                    return nested
        return ""
