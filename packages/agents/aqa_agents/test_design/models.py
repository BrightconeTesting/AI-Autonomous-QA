"""Test design agent I/O models."""

from typing import Any

from pydantic import BaseModel, Field


class TestDesignInput(BaseModel):
    app_map: dict[str, Any] | None = None
    max_tests: int = Field(default=10)
    priorities: list[str] = Field(default_factory=lambda: ["critical", "high"])


class TestDesignOutput(BaseModel):
    test_cases: list[dict[str, Any]] = Field(default_factory=list)
