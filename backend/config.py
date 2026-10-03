from functools import lru_cache
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Pharmacy Operations API"
    database_url: str = "sqlite:///./pharmacy.db"
    business_timezone: str = "Africa/Cairo"
    cookie_secure: bool = False
    environment: Literal["development", "production"] = "development"
    llm_model_id: str = "BioMistral/BioMistral-7B"
    llm_max_new_tokens: int = Field(default=160, ge=1, le=1024)
    llm_context_window: int = Field(default=2048, ge=64, le=32768)
    gemini_api_key: SecretStr | None = None
    chat_model_id: str = "gemini-3.8-flash"
    chat_max_output_tokens: int = Field(default=1800, ge=256, le=8192)

    @field_validator("business_timezone")
    @classmethod
    def validate_business_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown IANA timezone: {value}") from exc
        return value

    @model_validator(mode="after")
    def validate_public_deployment(self):
        if self.environment == "production":
            if self.database_url.startswith("sqlite"):
                raise ValueError("Production accounts require a persistent PostgreSQL database.")
            if not self.cookie_secure:
                raise ValueError("Production session cookies must use HTTPS.")
        return self

    @model_validator(mode="after")
    def validate_llm_context(self):
        if self.llm_max_new_tokens >= self.llm_context_window:
            raise ValueError("LLM_MAX_NEW_TOKENS must be smaller than LLM_CONTEXT_WINDOW.")
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
