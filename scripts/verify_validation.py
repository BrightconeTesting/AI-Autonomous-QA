#!/usr/bin/env python3
"""Verify ValidationModule: schema gate + stub validators."""

import sys

from aqa_shared.validation import ValidationModule, ValidationResult

VALID_CASE = {
    "name": "Login with valid credentials",
    "priority": "high",
    "steps": [
        {"action": "navigate", "target": "page:login"},
        {"action": "fill", "target": "element:username"},
        {"action": "click", "target": "element:submit"},
    ],
}

INVALID_CASE = {
    "priority": "high",
    "steps": [{"action": "click"}],
}


def _assert_result(label: str, result: ValidationResult, *, expect_valid: bool) -> None:
    if result.valid != expect_valid:
        raise AssertionError(f"{label}: expected valid={expect_valid}, got {result.model_dump()}")


def main() -> int:
    print("verify:validation")

    ok = ValidationModule.validate_test_case(VALID_CASE)
    _assert_result("validate_test_case(valid)", ok, expect_valid=True)
    print("OK validate_test_case: valid case passes")

    bad = ValidationModule.validate_test_case(INVALID_CASE)
    _assert_result("validate_test_case(invalid)", bad, expect_valid=False)
    if not bad.errors:
        raise AssertionError("expected schema errors for invalid test case")
    print(f"OK validate_test_case: invalid case rejected ({len(bad.errors)} errors)")

    for name, fn, arg in [
        ("validate_script", ValidationModule.validate_script, "// stub"),
        ("validate_locators", ValidationModule.validate_locators, "page.getByRole('button')"),
        ("validate_execution_plan", ValidationModule.validate_execution_plan, {"scripts": [], "parallelism": 1}),
    ]:
        result = fn(arg)
        _assert_result(name, result, expect_valid=True)
        print(f"OK {name}: stub returns valid")

    print("verify:validation OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
