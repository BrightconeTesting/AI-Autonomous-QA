"""Resolve Playwright locators from semantic target strings."""

from __future__ import annotations

import ast
import json
import re
from typing import Any


def _parse_json_string(value: str) -> str | None:
    value = value.strip()
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return None
    return parsed if isinstance(parsed, str) else None


def _parse_string_call(target: str, method: str) -> str | None:
    prefix = f"{method}("
    if not target.lower().startswith(prefix.lower()) or not target.endswith(")"):
        return None
    return _parse_json_string(target[len(prefix) : -1])


def _parse_get_by_role(target: str) -> tuple[str, str] | None:
    if not target.lower().startswith("getbyrole(") or not target.endswith(")"):
        return None
    inner = target[target.index("(") + 1 : -1]
    decoder = json.JSONDecoder()
    try:
        role, pos = decoder.raw_decode(inner.lstrip())
        rest = inner.lstrip()[pos:].lstrip()
    except json.JSONDecodeError:
        return None
    if not isinstance(role, str) or not rest.startswith(","):
        return None
    rest = rest[1:].lstrip()
    name_match = re.match(r"\{\s*name\s*:\s*", rest, re.IGNORECASE)
    if not name_match:
        return None
    try:
        name, end = decoder.raw_decode(rest[name_match.end() :])
    except json.JSONDecodeError:
        return None
    if not isinstance(name, str):
        return None
    trailing = rest[name_match.end() + end :].strip()
    if trailing != "}":
        return None
    return role, name


def _parse_locator_target(target: str) -> str | None:
    css_value = _parse_string_call(target, "locator")
    if css_value is None:
        return None
    if css_value.startswith("css="):
        return css_value[4:]
    return css_value


def resolve_locator(page, target: str):
    target = (target or "").strip()
    if not target:
        raise ValueError("Step target is empty")

    role_match = _parse_get_by_role(target)
    if role_match:
        role, name = role_match
        return page.get_by_role(role, name=name)

    for method, resolver in (
        ("getByLabel", page.get_by_label),
        ("getByPlaceholder", page.get_by_placeholder),
        ("getByText", page.get_by_text),
        ("getByTestId", page.get_by_test_id),
    ):
        value = _parse_string_call(target, method)
        if value is not None:
            return resolver(value)

    css = _parse_locator_target(target)
    if css is not None:
        return page.locator(css)

    return page.locator(target)


def run_step(page, step: dict[str, Any]) -> None:
    action = str(step.get("action") or "")
    target = str(step.get("target") or "")

    if action == "navigate":
        page.goto(target, wait_until="domcontentloaded", timeout=30000)
        return

    locator = resolve_locator(page, target)
    if action == "click":
        locator.click(timeout=15000)
    elif action == "fill":
        value = str(step.get("value") or "test")
        locator.fill(value, timeout=15000)
    elif action == "select":
        locator.select_option(label=str(step.get("value") or ""), timeout=15000)
    elif action == "hover":
        locator.hover(timeout=15000)
    elif action == "assertVisible":
        locator.wait_for(state="visible", timeout=15000)
    else:
        raise ValueError(f"Unsupported action: {action}")
