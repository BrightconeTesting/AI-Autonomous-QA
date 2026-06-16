"""Intelligence agent I/O models."""

from typing import Any

from pydantic import BaseModel, Field


class IntelligenceInput(BaseModel):
    run_results: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)


class IntelligenceOutput(BaseModel):
    coverage: float = Field(default=0.0)
