"""Execution plan validation (SPEC §13.3).

Stub: always valid until orchestrator wires script reference checks.
"""

from __future__ import annotations

from typing import Any

from aqa_shared.validation.types import ValidationResult


def validate_execution_plan(_plan: Any) -> ValidationResult:
    return ValidationResult(valid=True)
