"""Isolated Transformers-backed service for local, research-only LLM inference.

The rest of the application should depend on ``LLMService.generate`` rather
than importing Transformers, PyTorch, or Hugging Face classes directly.
Model output is unverified and is not authoritative pharmacy or medical advice.
"""

from __future__ import annotations

import threading
from typing import Any

from backend.config import Settings, get_settings


class LLMDependencyError(RuntimeError):
    """Raised when optional model runtime dependencies are unavailable."""


class LLMService:
    """Lazy-loaded text generation service with a stable model-neutral API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._tokenizer: Any | None = None
        self._model: Any | None = None
        self._torch: Any | None = None
        self._lock = threading.RLock()

    @property
    def model_id(self) -> str:
        """Return the configured Hugging Face repository or local model path."""
        return self._settings.llm_model_id

    def generate(self, prompt: str) -> str:
        """Generate one response for a single user prompt."""
        if not prompt or not prompt.strip():
            raise ValueError("Prompt must not be empty.")

        with self._lock:
            self._load_if_needed()
            assert self._tokenizer is not None
            assert self._model is not None
            assert self._torch is not None

            inputs = self._tokenizer.apply_chat_template(
                [{"role": "user", "content": prompt.strip()}],
                add_generation_prompt=True,
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
            )
            prompt_length = int(inputs["input_ids"].shape[-1])
            if prompt_length + self._settings.llm_max_new_tokens > self._settings.llm_context_window:
                raise ValueError(
                    "Prompt is too long for the configured context window. "
                    "Shorten the prompt or increase LLM_CONTEXT_WINDOW if the selected model supports it."
                )

            inputs = inputs.to(self._model.device)
            generation_options: dict[str, Any] = {
                "max_new_tokens": self._settings.llm_max_new_tokens,
                "do_sample": False,
                "use_cache": True,
            }
            if self._tokenizer.eos_token_id is not None:
                generation_options["pad_token_id"] = self._tokenizer.eos_token_id
                generation_options["eos_token_id"] = self._tokenizer.eos_token_id

            with self._torch.inference_mode():
                output_tokens = self._model.generate(**inputs, **generation_options)

            answer_tokens = output_tokens[0][prompt_length:]
            return self._tokenizer.decode(
                answer_tokens,
                skip_special_tokens=True,
            ).strip()

    def _load_if_needed(self) -> None:
        if self._model is not None and self._tokenizer is not None:
            return

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise LLMDependencyError(
                "LLM dependencies are missing. Install the project requirements in a supported "
                "Python environment before running the model."
            ) from exc

        self._torch = torch
        use_cuda = torch.cuda.is_available()
        if use_cuda:
            dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        else:
            dtype = torch.float32

        self._tokenizer = AutoTokenizer.from_pretrained(self.model_id)
        self._model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            device_map="auto",
            torch_dtype=dtype,
            use_safetensors=True,
        )
        self._model.eval()
