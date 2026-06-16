"""Validation gate result types (SPEC §13)."""

from pydantic import BaseModel, Field


class ValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
