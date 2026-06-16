"""Healing agent I/O models — output mirrors input (pass-through stub)."""

from typing import Any

from pydantic import BaseModel, Field


class HealingInput(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    error_context: str | None = None


class HealingOutput(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    error_context: str | None = None
