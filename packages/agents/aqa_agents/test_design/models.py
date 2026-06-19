"""Test design agent I/O models."""

from typing import Any

from pydantic import BaseModel, Field


class TestDesignInput(BaseModel):
    app_map: dict[str, Any] | None = None
    max_tests: int = Field(default=200, ge=1, le=200)
    priorities: list[str] = Field(default_factory=lambda: ["critical", "high", "medium"])
    use_llm: bool = True


class TestDesignOutput(BaseModel):
    test_cases: list[dict[str, Any]] = Field(default_factory=list)
