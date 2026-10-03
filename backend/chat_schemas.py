from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ChatHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def trim_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Chat messages cannot be blank.")
        return value


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[ChatHistoryMessage] = Field(default_factory=list, max_length=12)

    @field_validator("message")
    @classmethod
    def trim_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Ask a question before sending.")
        return value

    @model_validator(mode="after")
    def validate_history(self):
        total_characters = len(self.message)
        for index, entry in enumerate(self.history):
            expected_role = "user" if index % 2 == 0 else "assistant"
            if entry.role != expected_role:
                raise ValueError("Chat history must alternate user and assistant messages.")
            total_characters += len(entry.content)

        if len(self.history) % 2:
            raise ValueError("Chat history must end with a complete assistant response.")
        if total_characters > 16000:
            raise ValueError("This conversation is too long. Start a new chat to continue.")
        return self


class ChatResponse(BaseModel):
    answer: str

