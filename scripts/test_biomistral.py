"""Manual smoke test for the configured local Hugging Face model."""

from backend.llm import LLMService


def main() -> None:
    service = LLMService()
    question = (
        "Why should a pharmacy track medicine batch numbers and expiry dates? "
        "Give a short, general answer focused on inventory safety."
    )

    print("Research-only demo: verify this unreviewed model output against trusted sources.")
    print(f"Model: {service.model_id}")
    print(f"Question: {question}\n")
    print(service.generate(question))


if __name__ == "__main__":
    main()
