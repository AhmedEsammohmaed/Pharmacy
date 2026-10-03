"""Model-independent interface for local language model inference."""

from backend.llm.service import LLMDependencyError, LLMService

__all__ = ["LLMDependencyError", "LLMService"]
