"""Merge rule + LLM cases and enforce validation gates (Day 23, SPEC §13.1)."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from aqa_shared.validation import validate_test_case

from aqa_agents.test_design.templates import PRIORITY_RANK

logger = logging.getLogger(__name__)


def _normalize_name(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def collect_appmap_references(appmap: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    urls: set[str] = set()
    selectors: set[str] = set()
    flow_ids: set[str] = set()

    for page in appmap.get("pages") or []:
        raw = (page.get("url") or "").strip()
        if raw:
            urls.add(raw.rstrip("/"))

    for element in appmap.get("elements") or []:
        selector = (element.get("semantic_selector") or "").strip()
        if selector:
            selectors.add(selector)

    for flow in appmap.get("flows") or []:
        flow_id = flow.get("flow_id")
        if flow_id:
            flow_ids.add(str(flow_id))

    return urls, selectors, flow_ids


def _url_matches_appmap(target: str, urls: set[str]) -> bool:
    normalized = target.strip().rstrip("/")
    if normalized in urls:
        return True
    parsed = urlparse(normalized)
    path = parsed.path.rstrip("/")
    for known in urls:
        known_path = urlparse(known).path.rstrip("/")
        if path and known_path and path == known_path:
            return True
        if normalized.startswith(known.rstrip("/")):
            return True
    return False


def _selector_matches_appmap(target: str, selectors: set[str]) -> bool:
    cleaned = target.strip()
    if cleaned in selectors:
        return True
    return any(cleaned in selector or selector in cleaned for selector in selectors)


def _sanitize_step(
    step: dict[str, Any],
    *,
    urls: set[str],
    selectors: set[str],
) -> dict[str, Any] | None:
    action = str(step.get("action") or "").strip()
    target = str(step.get("target") or "").strip()
    if not action or not target:
        return None

    if action == "navigate":
        if _url_matches_appmap(target, urls):
            return {"action": action, "target": target, **{k: v for k, v in step.items() if k not in {"action", "target"}}}
        return None

    if _selector_matches_appmap(target, selectors) or _url_matches_appmap(target, urls):
        return {"action": action, "target": target, **{k: v for k, v in step.items() if k not in {"action", "target"}}}
    return None


def _sanitize_case_targets(
    case: dict[str, Any],
    *,
    urls: set[str],
    selectors: set[str],
    flow_ids: set[str],
) -> dict[str, Any] | None:
    raw_steps = case.get("steps") or []
    if not raw_steps:
        return None

    steps: list[dict[str, Any]] = []
    for step in raw_steps:
        if not isinstance(step, dict):
            continue
        sanitized = _sanitize_step(step, urls=urls, selectors=selectors)
        if sanitized is not None:
            steps.append(sanitized)

    if not steps:
        return None

    sanitized_case = dict(case)
    sanitized_case["steps"] = steps

    flow_id = sanitized_case.get("flow_id")
    if flow_id is not None and str(flow_id) not in flow_ids:
        sanitized_case.pop("flow_id", None)

    return sanitized_case


def merge_test_cases(
    rule_cases: list[dict[str, Any]],
    llm_cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Dedupe by case-insensitive name; keep higher priority."""
    merged: dict[str, dict[str, Any]] = {}

    for case in rule_cases + llm_cases:
        name = _normalize_name(str(case.get("name") or ""))
        if not name:
            continue
        existing = merged.get(name)
        if existing is None:
            merged[name] = case
            continue
        new_rank = PRIORITY_RANK.get(str(case.get("priority")), 99)
        old_rank = PRIORITY_RANK.get(str(existing.get("priority")), 99)
        if new_rank < old_rank:
            merged[name] = case

    return list(merged.values())


def validate_and_filter_cases(
    cases: list[dict[str, Any]],
    appmap: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Schema + AppMap grounding. Returns (accepted, rejection_reasons)."""
    urls, selectors, flow_ids = collect_appmap_references(appmap)
    accepted: list[dict[str, Any]] = []
    rejections: list[str] = []

    for case in cases:
        name = str(case.get("name") or "unnamed")
        grounded = _sanitize_case_targets(case, urls=urls, selectors=selectors, flow_ids=flow_ids)
        if grounded is None:
            rejections.append(f"{name}: empty or invalid steps after AppMap grounding")
            continue

        schema_result = validate_test_case(grounded)
        if not schema_result.valid:
            rejections.append(f"{name}: schema — {'; '.join(schema_result.errors[:3])}")
            continue

        accepted.append(grounded)

    if rejections:
        logger.info(
            "TestDesignAgent rejected cases during validation",
            extra={"rejectedCount": len(rejections), "acceptedCount": len(accepted)},
        )

    return accepted, rejections
