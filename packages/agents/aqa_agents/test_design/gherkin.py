"""Convert rule-based test cases to Cucumber Gherkin views (DASHBOARD-SPEC §6)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


def _human_url(url: str) -> str:
    parsed = urlparse(url)
    parts = [
        segment
        for segment in parsed.path.strip("/").split("/")
        if segment.lower() not in {"web", "index.php", "empnumber", "7", "empnumber"}
    ]
    if not parts:
        return "the home page"
    labels: list[str] = []
    for segment in parts[-3:]:
        spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", segment)
        spaced = spaced.replace("_", " ").replace("view", " ").strip()
        if spaced:
            labels.append(spaced.title())
    return "the " + " › ".join(labels) + " page"


def _humanize_target(target: str) -> str:
    text = (target or "").strip()
    if not text:
        return "the element"
    if text.startswith("http://") or text.startswith("https://"):
        return _human_url(text)

    role_match = re.search(
        r"getByRole\(['\"](\w+)['\"],\s*\{\s*name:\s*['\"](.+?)['\"]\s*\}\)",
        text,
    )
    if role_match:
        role, name = role_match.group(1), role_match.group(2)
        role_phrase = {
            "link": "link",
            "button": "button",
            "tab": "tab",
            "heading": "heading",
            "textbox": "field",
            "combobox": "dropdown",
            "menuitem": "menu item",
            "checkbox": "checkbox",
        }.get(role, role)
        return f'the "{name}" {role_phrase}'

    label_match = re.search(r"getByLabel\(['\"](.+?)['\"]\)", text)
    if label_match:
        return f'the "{label_match.group(1)}" field'

    placeholder_match = re.search(r"getByPlaceholder\(['\"](.+?)['\"]\)", text)
    if placeholder_match:
        return f'the "{placeholder_match.group(1)}" field'

    if text.startswith("locator("):
        css_match = re.search(r"name=['\"]?([^'\"]+)['\"]?", text)
        if css_match:
            return f'the "{css_match.group(1)}" element'
        href_match = re.search(r"href=['\"]([^'\"]+)['\"]", text)
        if href_match:
            return f'the link to {href_match.group(1)}'
        return "the target element"

    return text


def _action_phrase(action: str, target: str) -> str:
    human = _humanize_target(target)
    if action == "click":
        return f"I click {human}"
    if action == "fill":
        return f"I enter sample text in {human}"
    if action == "select":
        return f"I select an option in {human}"
    if action == "hover":
        return f"I hover over {human}"
    if action == "assertVisible":
        return f"I should see {human}"
    return f"I perform {action} on {human}"


def _tags_for_case(test_case: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    priority = str(test_case.get("priority") or "medium")
    tags.append(f"@{priority}")
    if test_case.get("destructive"):
        tags.append("@destructive")
    if test_case.get("flow_id"):
        tags.append("@flow-replay")
    if test_case.get("tags"):
        for tag in test_case["tags"]:
            if isinstance(tag, str) and tag.startswith("@"):
                tags.append(tag)
    return tags


def to_gherkin(test_case: dict[str, Any], *, app_name: str = "Application") -> dict[str, Any]:
    machine_steps = list(test_case.get("steps") or [])
    gherkin_steps: list[dict[str, Any]] = []
    seen_given = False

    for step in machine_steps:
        action = str(step.get("action") or "")
        target = str(step.get("target") or "")
        if action == "navigate":
            keyword = "Given" if not seen_given else "And"
            text = (
                f"I am on {_human_url(target)}"
                if target.startswith("http")
                else f"I am on {target}"
            )
            seen_given = True
        elif action == "assertVisible":
            keyword = "Then"
            text = _action_phrase(action, target)
        elif action in {"click", "fill", "select", "hover"}:
            keyword = "When"
            text = _action_phrase(action, target)
        else:
            keyword = "When"
            text = _action_phrase(action, target)

        gherkin_steps.append(
            {"keyword": keyword, "text": text, "action": action, "target": target}
        )

    feature = str(test_case.get("feature") or f"{app_name} flows")
    name = str(test_case.get("name") or "Scenario")

    return {
        "feature": feature,
        "scenario": name,
        "tags": _tags_for_case(test_case),
        "steps": gherkin_steps,
    }


def attach_gherkin(test_case: dict[str, Any], *, app_name: str = "Application") -> dict[str, Any]:
    return {
        "gherkin": to_gherkin(test_case, app_name=app_name),
        "steps": list(test_case.get("steps") or []),
        "destructive": bool(test_case.get("destructive")),
        "execution_order": test_case.get("execution_order") or "default",
    }


def render_feature_file(test_cases: list[dict[str, Any]], *, app_name: str = "Application") -> str:
    lines: list[str] = []
    current_feature: str | None = None

    for case in test_cases:
        gherkin = case.get("gherkin") or to_gherkin(case, app_name=app_name)
        feature = str(gherkin.get("feature") or f"{app_name} flows")
        if feature != current_feature:
            if current_feature is not None:
                lines.append("")
            lines.append(f"Feature: {feature}")
            current_feature = feature

        for tag in gherkin.get("tags") or []:
            lines.append(f"  {tag}")
        lines.append(f"  Scenario: {gherkin.get('scenario', 'Scenario')}")
        for step in gherkin.get("steps") or []:
            lines.append(f"    {step.get('keyword', 'When')} {step.get('text', '')}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"
