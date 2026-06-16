"""Deterministic validation gates for AI-generated artifacts (SPEC §13)."""

from aqa_shared.validation.types import ValidationResult
from aqa_shared.validation.validate_execution_plan import validate_execution_plan
from aqa_shared.validation.validate_locators import validate_locators
from aqa_shared.validation.validate_script import validate_script
from aqa_shared.validation.validate_test_case import validate_test_case


class ValidationModule:
    """Validation gate API — JSON Schema now; tsc/AST rules in Week 5–6."""

    validate_test_case = staticmethod(validate_test_case)
    validate_script = staticmethod(validate_script)
    validate_locators = staticmethod(validate_locators)
    validate_execution_plan = staticmethod(validate_execution_plan)


__all__ = [
    "ValidationModule",
    "ValidationResult",
    "validate_execution_plan",
    "validate_locators",
    "validate_script",
    "validate_test_case",
]
