#!/usr/bin/env python3
"""Verify Playwright step handler locator resolution."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "workers/playwright-executor"))

from aqa_executor.step_handlers import resolve_locator  # noqa: E402


def _assert_locator(page: MagicMock, method: str, *args) -> None:
    getattr(page, method).assert_called_once_with(*args)


def main() -> int:
    print("verify:step-handlers")
    page = MagicMock()

    cases = [
        (
            'getByRole("textbox", { name: "Search" })',
            "get_by_role",
            ("textbox",),
            {"name": "Search"},
        ),
        (
            'getByPlaceholder("Search subject, question, manufacturer…")',
            "get_by_placeholder",
            ("Search subject, question, manufacturer…",),
            {},
        ),
        (
            'getByLabel("Email address")',
            "get_by_label",
            ("Email address",),
            {},
        ),
        (
            'getByTestId("submit-btn")',
            "get_by_test_id",
            ("submit-btn",),
            {},
        ),
        (
            'getByText("Sign in")',
            "get_by_text",
            ("Sign in",),
            {},
        ),
        (
            "locator('css=input[name=\"q\"]')",
            "locator",
            ('input[name="q"]',),
            {},
        ),
        (
            "#open-modal",
            "locator",
            ("#open-modal",),
            {},
        ),
    ]

    for target, method, args, kwargs in cases:
        page.reset_mock()
        resolve_locator(page, target)
        if kwargs:
            getattr(page, method).assert_called_once_with(*args, **kwargs)
        else:
            _assert_locator(page, method, *args)

    print("verify:step-handlers OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
