"""Gemini-backed chat provider, isolated from the web routes and UI."""

from __future__ import annotations

from typing import Sequence

from backend.chat_schemas import ChatHistoryMessage
from backend.config import Settings, get_settings

SYSTEM_INSTRUCTION = """You are a helpful assistant in a pharmacy operations application.
Answer general and non-clinical pharmacy questions clearly and in useful detail.
Organize longer answers with short headings or numbered steps, explain unfamiliar
terms, and say when you are uncertain. Do not pretend to have checked live sources
or a verified pharmacy knowledge base.

This is not a clinical tool. Do not provide medical advice, diagnoses, treatment
recommendations, medication selection, or patient-specific directions about dose,
safety, interactions, or care. If a question asks for a clinical decision, explain
that you can only provide general non-clinical information and direct the user to a
licensed pharmacist or clinician. For possible emergencies, advise contacting local
emergency services or a poison center promptly. Never request identifying patient
details."""


class ChatProviderError(RuntimeError):
    """A safe, user-facing error from the configured chat provider."""


class ChatNotConfiguredError(ChatProviderError):
    """Raised when the provider API key is missing."""


class ChatRateLimitError(ChatProviderError):
    """Raised when the provider has exhausted its request quota."""


class GeminiChatService:
    """Generate multi-turn replies without exposing SDK types to callers."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def model_id(self) -> str:
        return self._settings.chat_model_id

    def reply(self, message: str, history: Sequence[ChatHistoryMessage]) -> str:
        api_key = self._settings.gemini_api_key
        if api_key is None or not api_key.get_secret_value().strip():
            raise ChatNotConfiguredError(
                "AI chat is not configured yet. Add GEMINI_API_KEY to the server environment."
            )

        try:
            from google import genai
            from google.genai import errors, types
        except ImportError as exc:
            raise ChatNotConfiguredError(
                "The Gemini SDK is missing. Install backend/requirements.txt and restart the app."
            ) from exc

        provider_history = [
            types.Content(
                role="model" if item.role == "assistant" else "user",
                parts=[types.Part.from_text(text=item.content)],
            )
            for item in history
        ]

        client = None
        try:
            client = genai.Client(
                api_key=api_key.get_secret_value(),
                http_options=types.HttpOptions(timeout=60000),
            )
            chat = client.chats.create(
                model=self.model_id,
                history=provider_history,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    max_output_tokens=self._settings.chat_max_output_tokens,
                ),
            )
            response = chat.send_message(message)
        except errors.APIError as exc:
            if str(getattr(exc, "code", "")) == "429":
                raise ChatRateLimitError(
                    "The free AI request limit has been reached. Please wait a little and try again."
                ) from exc
            raise ChatProviderError(
                "The AI service could not answer right now. Please try again shortly."
            ) from exc
        except Exception as exc:
            # Avoid returning SDK/network diagnostics to public users.
            raise ChatProviderError(
                "The AI service could not answer right now. Please try again shortly."
            ) from exc
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass

        answer = (response.text or "").strip()
        if not answer:
            raise ChatProviderError(
                "The AI could not provide a response to that message. Please rephrase it."
            )
        return answer
