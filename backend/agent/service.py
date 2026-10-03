"""Coordinate the pharmacy's read-only data tools with the configured LLM."""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.agent.tools import PHARMACY_TOOL_DECLARATIONS, PharmacyReadOnlyTools
from backend.chat_schemas import ChatHistoryMessage
from backend.config import Settings, get_settings
from backend.llm.gemini_service import GeminiChatService
from backend.llm.n8n_service import N8NChatService


class PharmacyAgent:
    """Answer pharmacy-work questions using tenant-scoped, read-only tools."""

    def __init__(
        self,
        llm: GeminiChatService | None = None,
        n8n: N8NChatService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._llm = llm or GeminiChatService()
        self._n8n = n8n or N8NChatService(self._settings)

    def reply(
        self,
        message: str,
        history: list[ChatHistoryMessage],
        db: Session,
        tenant_id: int,
    ) -> str:
        if self._settings.chat_provider == "n8n":
            return self._n8n.reply(message, history, tenant_id)

        tools = PharmacyReadOnlyTools(db, tenant_id)
        return self._llm.reply(
            message,
            history,
            tool_declarations=PHARMACY_TOOL_DECLARATIONS,
            tool_executor=tools.execute,
        )

    async def reply_cloudflare(
        self,
        message: str,
        history: list[ChatHistoryMessage],
        db: Session,
        tenant_id: int,
    ) -> str:
        """Use Cloudflare's asynchronous fetch API without changing local providers."""
        from backend.llm.cloudflare_service import CloudflareChatService

        tools = PharmacyReadOnlyTools(db, tenant_id)
        return await CloudflareChatService(self._settings).reply(
            message,
            history,
            tenant_id,
            tool_declarations=PHARMACY_TOOL_DECLARATIONS,
            tool_executor=tools.execute,
        )
