"""JSON Schema validation for LLM-generated test cases (SPEC §13.1)."""

from __future__ import annotations

from typing import Any

import jsonschema

from aqa_shared.validation._schema_loader import load_schema
from aqa_shared.validation.types import ValidationResult

_TEST_CASE_SCHEMA = load_schema("test-case.schema.json")
_VALIDATOR = jsonschema.Draft202012Validator(_TEST_CASE_SCHEMA)


def validate_test_case(data: Any) -> ValidationResult:
    errors = sorted(
        f"{'.'.join(str(part) for part in err.path) or 'root'}: {err.message}"
        for err in _VALIDATOR.iter_errors(data)
    )
    return ValidationResult(valid=not errors, errors=errors)
