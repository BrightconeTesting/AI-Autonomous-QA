"""Locator policy static analysis (SPEC §12, §13.2).

Stub: always valid until Week 5–6 adds AST rules.
"""

from __future__ import annotations

from aqa_shared.validation.types import ValidationResult


def validate_locators(_code: str) -> ValidationResult:
    return ValidationResult(valid=True)
