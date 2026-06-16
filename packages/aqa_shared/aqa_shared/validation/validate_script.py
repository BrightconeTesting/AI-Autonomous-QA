"""TypeScript compile gate for generated Playwright scripts (SPEC §13.2).

Stub: always valid until Week 5–6 adds ``tsc --noEmit``.
"""

from __future__ import annotations

from aqa_shared.validation.types import ValidationResult


def validate_script(_code: str) -> ValidationResult:
    return ValidationResult(valid=True)
