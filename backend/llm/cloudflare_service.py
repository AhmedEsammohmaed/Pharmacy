"""Async chat adapter for Google Gemini or n8n on Cloudflare Python Workers.

This module uses the Worker's JavaScript ``fetch`` runtime API through Pyodide's
FFI. It is only imported when the Cloudflare chat route is selected.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any
from urllib.parse import quote

from backend.chat_schemas import ChatHistoryMessage
from backend.config import Settings, get_settings
from backend.llm.gemini_service import (
    ChatNotConfiguredError,
    ChatProviderError,
    ChatRateLimitError,
    SYSTEM_INSTRUCTION,
)
from backend.n8n_security import issue_tool_access_token


class CloudflareChatService:
    """Keep Cloudflare's FFI and network details isolated from agent tools."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def reply(
        self,
        message: str,
        history: Sequence[ChatHistoryMessage],
        tenant_id: int,
        *,
        tool_declarations: Sequence[Mapping[str, Any]] = (),
        tool_executor: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    ) -> str:
        if self._settings.chat_provider == "n8n":
            return await self._reply_n8n(message, history, tenant_id)
        return await self._reply_gemini(
            message,
            history,
            tool_declarations=tool_declarations,
            tool_executor=tool_executor,
        )

    async def _post_json(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> tuple[int, str]:
        try:
            from js import Object, fetch
            from pyodide.ffi import to_js

            options = to_js(
                {
                    "method": "POST",
                    "headers": headers,
                    "body": json.dumps(payload, separators=(",", ":")),
                    "redirect": "manual",
                },
                dict_converter=Object.fromEntries,
            )
            response = await fetch(url, options)
            body = await response.text()
            if len(body) > 1_000_000:
                raise ChatProviderError("The AI provider returned an oversized response.")
            return int(response.status), body
        except ChatProviderError:
            raise
        except Exception as exc:
            raise ChatProviderError(
                "The AI service could not answer right now. Please try again shortly."
            ) from exc

    async def _reply_gemini(
        self,
        message: str,
        history: Sequence[ChatHistoryMessage],
        *,
        tool_declarations: Sequence[Mapping[str, Any]],
        tool_executor: Callable[[str, dict[str, Any]], dict[str, Any]] | None,
    ) -> str:
        key_value = self._settings.gemini_api_key
        api_key = key_value.get_secret_value().strip() if key_value else ""
        if not api_key:
            raise ChatNotConfiguredError(
                "AI chat is not configured yet. Add GEMINI_API_KEY to the Worker secrets."
            )
        if tool_declarations and tool_executor is None:
            raise ChatProviderError("The pharmacy tools could not be initialized.")

        contents = [
            {
                "role": "model" if item.role == "assistant" else "user",
                "parts": [{"text": item.content}],
            }
            for item in history
        ]
        contents.append({"role": "user", "parts": [{"text": message}]})
        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": self._settings.chat_max_output_tokens,
            },
        }
        if tool_declarations:
            payload["tools"] = [
                {"functionDeclarations": [dict(item) for item in tool_declarations]}
            ]
            payload["toolConfig"] = {
                "functionCallingConfig": {"mode": "AUTO"},
            }

        model = quote(self._settings.chat_model_id, safe="-._")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        response_body: dict[str, Any] = {}
        for tool_round in range(4):
            status_code, body = await self._post_json(
                url,
                payload,
                {"Content-Type": "application/json", "x-goog-api-key": api_key},
            )
            if status_code == 429:
                raise ChatRateLimitError(
                    "The free AI request limit has been reached. Please wait a little and try again."
                )
            if not 200 <= status_code < 300:
                raise ChatProviderError(
                    "The AI service could not answer right now. Please try again shortly."
                )
            try:
                response_body = json.loads(body)
            except ValueError as exc:
                raise ChatProviderError(
                    "The AI service returned an unreadable response. Please try again shortly."
                ) from exc

            candidates = response_body.get("candidates") or []
            candidate = next(
                (
                    item
                    for item in candidates
                    if isinstance(item, dict) and isinstance(item.get("content"), dict)
                ),
                None,
            )
            content = candidate.get("content", {}) if candidate else {}
            parts = content.get("parts") or []
            calls = [
                part["functionCall"]
                for part in parts
                if isinstance(part, dict) and isinstance(part.get("functionCall"), dict)
            ]
            if not calls:
                break
            if tool_round == 3 or tool_executor is None:
                raise ChatProviderError(
                    "The assistant could not finish using the pharmacy data. Try a more focused question."
                )

            contents.append(content)
            function_responses = []
            for call in calls:
                name = call.get("name")
                arguments = call.get("args") or {}
                if not isinstance(name, str) or not isinstance(arguments, dict):
                    result = {"error": "The requested pharmacy information could not be retrieved."}
                    name = name if isinstance(name, str) else "unknown"
                else:
                    try:
                        result = tool_executor(name, arguments)
                    except Exception:
                        result = {"error": "The requested pharmacy information could not be retrieved."}
                response_part: dict[str, Any] = {
                    "functionResponse": {"name": name, "response": {"result": result}}
                }
                if call.get("id"):
                    response_part["functionResponse"]["id"] = call["id"]
                function_responses.append(response_part)
            contents.append({"role": "user", "parts": function_responses})

        candidates = response_body.get("candidates") or []
        candidate = next(
            (
                item
                for item in candidates
                if isinstance(item, dict) and isinstance(item.get("content"), dict)
            ),
            None,
        )
        final_parts = candidate.get("content", {}).get("parts", []) if candidate else []
        answer = "".join(
            part.get("text", "")
            for part in final_parts
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ).strip()
        if not answer:
            raise ChatProviderError(
                "The AI could not provide a response to that message. Please rephrase it."
            )
        return answer

    async def _reply_n8n(
        self,
        message: str,
        history: Sequence[ChatHistoryMessage],
        tenant_id: int,
    ) -> str:
        url = self._settings.n8n_chat_webhook_url
        token_value = self._settings.n8n_chat_webhook_token
        secret = token_value.get_secret_value().strip() if token_value else ""
        if not url or not secret:
            raise ChatNotConfiguredError(
                "n8n chat is selected but not configured. Set its Worker secrets first."
            )

        payload = {
            "event": "pharmacy.chat.message",
            "message": message,
            "history": [item.model_dump() for item in history],
            "pharmacy_id": tenant_id,
            "tool_access_token": issue_tool_access_token(tenant_id, secret),
        }
        status_code, body_text = await self._post_json(
            url,
            payload,
            {
                "Authorization": f"Bearer {secret}",
                "Content-Type": "application/json",
            },
        )
        if status_code == 429:
            raise ChatRateLimitError(
                "The n8n workflow is receiving too many requests. Please wait and try again."
            )
        if not 200 <= status_code < 300:
            raise ChatProviderError(
                "The n8n workflow could not answer right now. Check its webhook and try again."
            )
        try:
            body: Any = json.loads(body_text)
        except ValueError:
            body = body_text
        answer = self._extract_answer(body)
        if not answer:
            raise ChatProviderError(
                "The n8n workflow returned no chat answer. Configure it to return an output field."
            )
        return answer

    @classmethod
    def _extract_answer(cls, body: Any) -> str:
        if isinstance(body, str):
            return body.strip()
        if not isinstance(body, dict):
            return ""
        for key in ("output", "answer", "text", "response"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, dict):
                nested = cls._extract_answer(value)
                if nested:
                    return nested
        return ""
