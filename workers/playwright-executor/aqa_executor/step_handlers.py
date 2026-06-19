"""Resolve Playwright locators from semantic target strings."""

from __future__ import annotations

import re


_ROLE_PATTERN = re.compile(
    r"getByRole\(\s*['\"](\w+)['\"]\s*,\s*\{\s*name:\s*['\"](.+?)['\"]\s*\}\s*\)",
    re.IGNORECASE,
)


def resolve_locator(page, target: str):
    target = (target or "").strip()
    if not target:
        raise ValueError("Step target is empty")

    role_match = _ROLE_PATTERN.match(target)
    if role_match:
        role, name = role_match.groups()
        return page.get_by_role(role, name=name)

    if target.startswith("getByText("):
        inner = target[len("getByText(") : -1].strip().strip("'\"")
        return page.get_by_text(inner)

    return page.locator(target)


def run_step(page, step: dict) -> None:
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
