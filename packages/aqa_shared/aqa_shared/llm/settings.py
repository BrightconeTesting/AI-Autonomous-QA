"""Environment-backed LLM settings (SPEC §32)."""

from __future__ import annotations

import os

# gpt-4o-mini list pricing (USD per token) — update when OpenAI changes rates.
_OPENAI_MINI_INPUT_USD = 0.15 / 1_000_000
_OPENAI_MINI_OUTPUT_USD = 0.60 / 1_000_000


def openai_api_key() -> str | None:
    value = os.getenv("OPENAI_API_KEY", "").strip()
    return value or None


def openai_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-5.5-mini").strip() or "gpt-5.5-mini"


def llm_available(*, use_llm: bool) -> bool:
    return bool(use_llm and openai_api_key())


def estimate_cost_usd(*, prompt_tokens: int, completion_tokens: int, model: str | None = None) -> float:
    """Rough USD estimate for budget tracking."""
    _ = model or openai_model()
    return (prompt_tokens * _OPENAI_MINI_INPUT_USD) + (completion_tokens * _OPENAI_MINI_OUTPUT_USD)
