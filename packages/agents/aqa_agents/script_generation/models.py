"""Script generation agent I/O models."""

from typing import Any

from pydantic import BaseModel, Field


class ScriptGenerationInput(BaseModel):
    test_case: dict[str, Any] = Field(default_factory=dict)
    selectors: dict[str, Any] = Field(default_factory=dict)
    framework: str = Field(default="playwright")


class ScriptGenerationOutput(BaseModel):
    code: str = Field(default="// stub")
