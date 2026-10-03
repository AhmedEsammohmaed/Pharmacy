"""Manually send a non-clinical pharmacy question to the configured Gemini model."""

from backend.llm.gemini_service import ChatProviderError, GeminiChatService


def main() -> int:
    question = "Explain FEFO inventory management in a pharmacy, with a practical example."
    try:
        answer = GeminiChatService().reply(question, history=[])
    except ChatProviderError as exc:
        print(f"Gemini chat failed: {exc}")
        return 1

    print(f"Question: {question}\n")
    print(f"Answer:\n{answer}")
    print("\nAI output is unverified; do not use it for clinical decisions or patient care.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
