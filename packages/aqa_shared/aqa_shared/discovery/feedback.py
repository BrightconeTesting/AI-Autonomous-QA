"""Execution feedback loop for Discovery (Phase H §9.10)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

FAILURE_LOCATOR_NOT_FOUND = "locator_not_found"
FAILURE_API_ERROR = "api_error"
FAILURE_FLOW_STEP_TIMEOUT = "flow_step_timeout"
FAILURE_AUTH_401 = "auth_401"

TESTABILITY_PENALTY = 15
API_CONFIDENCE_PENALTY = 0.15
FLOW_COMPLEXITY_BONUS = 10

_LOCATOR_PATTERNS = (
    re.compile(r"waiting for locator", re.I),
    re.compile(r"locator\.(?:click|fill|hover|select_option)", re.I),
    re.compile(r"strict mode violation", re.I),
    re.compile(r"element\(s\) not found", re.I),
    re.compile(r"no element matches", re.I),
)

_TIMEOUT_PATTERNS = (
    re.compile(r"timeout", re.I),
    re.compile(r"timed out", re.I),
)

_AUTH_PATTERNS = (
    re.compile(r"\b401\b"),
    re.compile(r"unauthorized", re.I),
    re.compile(r"authentication required", re.I),
)

_API_ERROR_PATTERNS = (
    re.compile(r"\b(?:4\d{2}|5\d{2})\b"),
    re.compile(r"status code \d{3}", re.I),
    re.compile(r"http.*(?:4\d{2}|5\d{2})", re.I),
    re.compile(r"api.*(?:failed|error)", re.I),
)


def classify_execution_failure(
    error_msg: str,
    *,
    step: dict[str, Any] | None = None,
    page_url: str | None = None,
) -> str | None:
    """Map Playwright executor error text to a discovery feedback failure type."""
    message = (error_msg or "").strip()
    if not message:
        return None

    action = str((step or {}).get("action") or "").lower()
    if any(pattern.search(message) for pattern in _AUTH_PATTERNS):
        return FAILURE_AUTH_401

    if action == "navigate" and any(pattern.search(message) for pattern in _API_ERROR_PATTERNS):
        return FAILURE_API_ERROR

    if action in {"click", "fill", "select", "hover", "assertVisible"}:
        if any(pattern.search(message) for pattern in _TIMEOUT_PATTERNS):
            if re.search(r"waiting for locator", message, re.I):
                return FAILURE_LOCATOR_NOT_FOUND
            return FAILURE_FLOW_STEP_TIMEOUT

    if any(pattern.search(message) for pattern in _LOCATOR_PATTERNS):
        return FAILURE_LOCATOR_NOT_FOUND

    if any(pattern.search(message) for pattern in _TIMEOUT_PATTERNS):
        return FAILURE_LOCATOR_NOT_FOUND

    if any(pattern.search(message) for pattern in _API_ERROR_PATTERNS):
        return FAILURE_API_ERROR

    if action in {"click", "fill", "select", "hover", "assertVisible"}:
        return FAILURE_LOCATOR_NOT_FOUND

    return None


def build_feedback_event(
    *,
    failure_type: str,
    error_msg: str,
    pipeline_run_id: str | None = None,
    testcase_id: str | None = None,
    step_index: int | None = None,
    step: dict[str, Any] | None = None,
    page_url: str | None = None,
) -> dict[str, Any]:
    """Create an append-only discovery feedback record."""
    step = step or {}
    return {
        "feedback_id": str(uuid.uuid4()),
        "failure_type": failure_type,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_run_id": pipeline_run_id,
        "testcase_id": testcase_id,
        "step_index": step_index,
        "error": (error_msg or "")[:2000],
        "action": step.get("action"),
        "target": step.get("target"),
        "page_url": page_url or step.get("url"),
        "flow_id": step.get("flow_id"),
        "element_id": step.get("element_id"),
        "api_endpoint_id": step.get("api_endpoint_id"),
        "requires_recrawl": failure_type == FAILURE_LOCATOR_NOT_FOUND,
    }


def normalize_feedback_events(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    events: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict) and item.get("failure_type"):
            events.append(dict(item))
    return events


def append_feedback_to_crawl_config(
    crawl_config: dict[str, Any] | None,
    event: dict[str, Any],
    *,
    max_events: int = 500,
) -> dict[str, Any]:
    """Append feedback event to application crawl_config (append-only)."""
    config = dict(crawl_config or {})
    events = normalize_feedback_events(config.get("discovery_feedback"))
    events.append(event)
    if len(events) > max_events:
        events = events[-max_events:]
    config["discovery_feedback"] = events
    return config


def urls_requiring_recrawl(feedback_events: list[dict[str, Any]] | None) -> set[str]:
    urls: set[str] = set()
    for event in normalize_feedback_events(feedback_events):
        if not event.get("requires_recrawl"):
            continue
        page_url = str(event.get("page_url") or "").strip()
        if page_url:
            urls.add(page_url.rstrip("/"))
    return urls


def _normalize_url(url: str) -> str:
    return url.split("?")[0].rstrip("/")


def _match_element(element: dict[str, Any], target: str | None) -> bool:
    if not target:
        return False
    selector = str(element.get("semantic_selector") or "")
    xpath = str(element.get("xpath_fallback") or "")
    element_id = str(element.get("element_id") or "")
    if element_id and element_id == target:
        return True
    if selector and selector == target:
        return True
    if xpath and xpath == target:
        return True
    return target in selector or target in xpath


def _match_api_mapping(
    mapping: dict[str, Any],
    *,
    endpoint_id: str | None,
    error_msg: str,
) -> bool:
    if endpoint_id and str(mapping.get("api_endpoint_id") or "") == endpoint_id:
        return True
    path_hint = str(mapping.get("path_pattern") or mapping.get("path") or "")
    if path_hint and path_hint in error_msg:
        return True
    return False


def _match_flow_step(flow: dict[str, Any], *, target: str | None, step_index: int | None) -> bool:
    steps = [s for s in (flow.get("steps") or []) if isinstance(s, dict)]
    if step_index is not None and 0 <= step_index < len(steps):
        step = steps[step_index]
        if target and str(step.get("target") or "") == target:
            return True
    if target:
        return any(str(step.get("target") or "") == target for step in steps)
    return False


def apply_discovery_feedback(
    appmap: dict[str, Any],
    feedback_events: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Adjust AppMap scores from execution feedback without mutating selectors."""
    events = normalize_feedback_events(feedback_events)
    if not events:
        return appmap

    updated = dict(appmap)
    elements = [dict(item) for item in (updated.get("elements") or [])]
    flows = [dict(item) for item in (updated.get("flows") or [])]
    mappings = [dict(item) for item in (updated.get("api_ui_mappings") or [])]
    auth_intelligence = dict(updated.get("auth_intelligence") or {})
    protected_pages = list(auth_intelligence.get("protected") or [])

    applied_count = 0
    recrawl_urls: set[str] = set()

    for event in events:
        failure_type = str(event.get("failure_type") or "")
        target = str(event.get("target") or "") or None
        error_msg = str(event.get("error") or "")
        page_url = str(event.get("page_url") or "")
        element_id = str(event.get("element_id") or "") or None
        endpoint_id = str(event.get("api_endpoint_id") or "") or None
        flow_id = str(event.get("flow_id") or "") or None
        step_index = event.get("step_index")

        if failure_type == FAILURE_LOCATOR_NOT_FOUND:
            for element in elements:
                if element_id and str(element.get("element_id") or "") != element_id:
                    if not _match_element(element, target):
                        continue
                elif not _match_element(element, target):
                    continue
                current = int(element.get("testability_score") or 50)
                element["testability_score"] = max(0, current - TESTABILITY_PENALTY)
                factors = list(element.get("feedback_factors") or [])
                factors.append("execution:locator_not_found")
                element["feedback_factors"] = sorted(set(factors))
                applied_count += 1
            if page_url:
                recrawl_urls.add(_normalize_url(page_url))

        elif failure_type == FAILURE_API_ERROR:
            for mapping in mappings:
                if not _match_api_mapping(mapping, endpoint_id=endpoint_id, error_msg=error_msg):
                    continue
                confidence = float(mapping.get("confidence") or 0.7)
                mapping["confidence"] = max(0.0, round(confidence - API_CONFIDENCE_PENALTY, 3))
                factors = list(mapping.get("feedback_factors") or [])
                factors.append("execution:api_error")
                mapping["feedback_factors"] = sorted(set(factors))
                applied_count += 1

        elif failure_type == FAILURE_FLOW_STEP_TIMEOUT:
            for flow in flows:
                if flow_id and str(flow.get("flow_id") or "") != flow_id:
                    continue
                if flow_id or _match_flow_step(flow, target=target, step_index=step_index):
                    complexity = int(flow.get("automation_complexity_score") or 30)
                    flow["automation_complexity_score"] = min(100, complexity + FLOW_COMPLEXITY_BONUS)
                    factors = list(flow.get("complexity_factors") or [])
                    factors.append("execution:step_timeout")
                    flow["complexity_factors"] = sorted(set(factors))
                    applied_count += 1
                    if not flow_id:
                        break

        elif failure_type == FAILURE_AUTH_401:
            if page_url:
                normalized = _normalize_url(page_url)
                if normalized not in protected_pages:
                    protected_pages.append(normalized)
                    applied_count += 1

    if protected_pages:
        auth_intelligence["protected"] = sorted(set(protected_pages))
        updated["auth_intelligence"] = auth_intelligence

    updated["elements"] = elements
    updated["flows"] = flows
    updated["api_ui_mappings"] = mappings
    updated["discovery_feedback_applied"] = {
        "event_count": len(events),
        "adjustments_applied": applied_count,
        "recrawl_urls": sorted(recrawl_urls),
    }
    return updated
