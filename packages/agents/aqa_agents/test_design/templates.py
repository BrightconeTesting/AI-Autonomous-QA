"""Rule-based test case templates from AppMap (Day 22, SPEC §17.2, §32.3).

Converts crawled AppMap v2 documents (pages, elements, flows, states) into draft
test cases without LLM involvement. Safe scenarios run first; destructive actions
(logout, delete, submit) are generated separately and scheduled last.

Example output shape::

    {
        "name": "Settings module path 1 — interaction replay",
        "priority": "critical",
        "flow_id": "<uuid>",
        "destructive": false,
        "execution_order": "default",
        "steps": [
            {"action": "navigate", "target": "https://example.com/app/settings"},
            {"action": "click", "target": "getByRole('tab', { name: 'Profile' })"},
        ],
    }
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

INTERACTION_ACTIONS = frozenset({"click", "hover", "select", "fill"})
PRIORITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
EXECUTION_ORDER_LAST = "last"
MAX_DESTRUCTIVE_CASES = 5

# Labels that mark session-ending or data-mutating actions — generated as tests but run last.
DESTRUCTIVE_LABELS = frozenset(
    label.lower()
    for label in (
        "logout",
        "log out",
        "sign out",
        "delete",
        "remove",
        "deactivate",
        "submit",
    )
)


def _normalize_name(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _url_label(url: str) -> str:
    path = urlparse(url).path.strip("/")
    parts = [
        segment
        for segment in path.split("/")
        if segment.lower() not in {"web", "index.php", "empnumber", "7"}
    ]
    if not parts:
        return "Home"
    last = parts[-1]
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", last)
    spaced = spaced.replace("_", " ").replace("view", " ").strip() or last
    return spaced.title()


def _page_label(page: dict[str, Any] | None, url: str = "") -> str:
    if page and page.get("title"):
        title = str(page["title"]).strip()
        if title:
            return title
    return _url_label(url)


def _page_for_url(indices: dict[str, Any], url: str) -> dict[str, Any] | None:
    normalized = url.rstrip("/")
    for page in indices["pages_by_id"].values():
        page_url = str(page.get("url") or "").rstrip("/")
        if page_url == normalized:
            return page
    return None


def _flow_feature_name(flow: dict[str, Any], *, app_module: str = "Application") -> str:
    raw = (flow.get("name") or "Flows").split("→")[0].strip()
    raw = raw.replace(" (CIC)", "").strip()
    if raw:
        return f"{app_module}: {raw.split(' path')[0].strip()}"
    return f"{app_module} flows"


def _flow_scenario_name(flow: dict[str, Any], indices: dict[str, Any]) -> str:
    """Build a unique, human-readable scenario title from flow steps."""
    raw_steps = flow.get("steps") or []
    landing_url = ""
    clicks: list[str] = []
    for step in raw_steps:
        action = step.get("action") or ""
        if action == "navigate":
            landing_url = (step.get("url") or "").strip()
        elif action == "click":
            label = (step.get("text_content") or "").strip()
            if label and not _is_destructive_text(label):
                clicks.append(label)

    page = _page_for_url(indices, landing_url) if landing_url else None
    landing = _page_label(page, landing_url)
    prefix = (flow.get("name") or "Flow").replace(" (CIC)", "").strip()

    if clicks:
        action_path = " → ".join(clicks[:4])
        return f"{prefix} on {landing}: {action_path}"
    if landing_url:
        return f"Open {landing} ({prefix})"
    return prefix or "Application flow replay"


def _case_dedupe_key(case: dict[str, Any]) -> str:
    flow_id = case.get("flow_id")
    if flow_id:
        return f"flow:{flow_id}"
    steps = case.get("steps") or []
    payload = json.dumps(steps, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _step_target(step: dict[str, Any]) -> str | None:
    selector = (step.get("semantic_selector") or "").strip()
    if selector:
        return selector
    role = (step.get("role") or "").strip()
    text = (step.get("text_content") or "").strip()
    if role and text:
        escaped = text.replace("'", "\\'")
        return f"getByRole('{role}', {{ name: '{escaped}' }})"
    url = (step.get("url") or "").strip()
    if url:
        return url
    return None


def _element_target(element: dict[str, Any]) -> str | None:
    selector = (element.get("semantic_selector") or "").strip()
    if selector:
        return selector
    role = (element.get("role") or "").strip()
    text = (element.get("text_content") or "").strip()
    tag = (element.get("tag_name") or "").strip().lower()
    if role and text:
        escaped = text.replace("'", "\\'")
        return f"getByRole('{role}', {{ name: '{escaped}' }})"
    if tag in {"input", "textarea", "select", "button", "a"} and text:
        escaped = text.replace("'", "\\'")
        if tag == "a":
            return f"getByRole('link', {{ name: '{escaped}' }})"
        if tag == "button":
            return f"getByRole('button', {{ name: '{escaped}' }})"
        return f"getByLabel('{escaped}')"
    return None


def _is_destructive_text(text: str | None) -> bool:
    lowered = (text or "").strip().lower()
    if not lowered:
        return False
    return any(token in lowered for token in DESTRUCTIVE_LABELS)


def _destructive_case(
    *,
    name: str,
    steps: list[dict[str, str]],
    flow_id: str | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "priority": "low",
        "flow_id": flow_id,
        "destructive": True,
        "execution_order": EXECUTION_ORDER_LAST,
        "steps": steps,
    }


def _pick_assertion_target(elements: list[dict[str, Any]]) -> str | None:
    for preferred_role in ("heading", "link", "button", "tab", "textbox"):
        for element in elements:
            if element.get("role") == preferred_role:
                target = _element_target(element)
                if target and not _is_destructive_text(element.get("text_content")):
                    return target
    for element in elements:
        if _is_destructive_text(element.get("text_content")):
            continue
        target = _element_target(element)
        if target:
            return target
    return None


def _build_indices(appmap: dict[str, Any]) -> dict[str, Any]:
    states = appmap.get("states") or []
    state_key_to_id = {
        state.get("state_key"): str(state.get("state_id"))
        for state in states
        if state.get("state_key")
    }
    by_page: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_state_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for element in appmap.get("elements") or []:
        page_id = str(element.get("page_id") or "")
        if page_id:
            by_page[page_id].append(element)
        state_id = element.get("state_id")
        if state_id:
            by_state_id[str(state_id)].append(element)
    pages_by_id = {str(page.get("page_id")): page for page in appmap.get("pages") or []}
    return {
        "by_page": by_page,
        "by_state_id": by_state_id,
        "state_key_to_id": state_key_to_id,
        "pages_by_id": pages_by_id,
    }


def _elements_for_state(indices: dict[str, Any], state_key: str | None) -> list[dict[str, Any]]:
    if not state_key:
        return []
    state_id = indices["state_key_to_id"].get(state_key)
    if not state_id:
        return []
    return list(indices["by_state_id"].get(state_id, []))


def _flow_has_interaction(flow: dict[str, Any]) -> bool:
    return any((step.get("action") or "") in INTERACTION_ACTIONS for step in flow.get("steps") or [])


def _flow_step_is_destructive(flow_step: dict[str, Any]) -> bool:
    return _is_destructive_text(flow_step.get("text_content"))


def template_flow_replay(
    flow: dict[str, Any], indices: dict[str, Any]
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Replay AppMap flow steps — safe steps only; destructive steps returned separately.

    For a flow like ``navigate → click tab → click delete``, the safe replay stops
    before the delete step and emits a separate destructive case for the delete click.
    """
    raw_steps = flow.get("steps") or []
    if not raw_steps:
        return None, []

    steps: list[dict[str, str]] = []
    destructive_cases: list[dict[str, Any]] = []
    last_navigate_url = ""

    for flow_step in raw_steps:
        action = flow_step.get("action") or "navigate"
        if action == "navigate":
            url = (flow_step.get("url") or "").strip()
            if not url:
                continue
            last_navigate_url = url
            steps.append({"action": "navigate", "target": url})
            page_id = str(flow_step.get("page_id") or "")
            assertion = _pick_assertion_target(indices["by_page"].get(page_id, []))
            if assertion:
                steps.append({"action": "assertVisible", "target": assertion})
            continue

        if action not in INTERACTION_ACTIONS:
            continue

        if _flow_step_is_destructive(flow_step):
            target = _step_target(flow_step)
            if target and last_navigate_url:
                label = (flow_step.get("text_content") or "destructive action").strip()[:60]
                destructive_cases.append(
                    _destructive_case(
                        name=f"{flow.get('name') or 'Flow'} — {label} (destructive)",
                        flow_id=flow.get("flow_id"),
                        steps=[
                            {"action": "navigate", "target": last_navigate_url},
                            {"action": action, "target": target},
                        ],
                    )
                )
            continue

        target = _step_target(flow_step)
        if not target:
            continue
        steps.append({"action": action, "target": target})
        state_elements = _elements_for_state(indices, flow_step.get("state_key"))
        assertion = _pick_assertion_target(state_elements)
        if assertion:
            steps.append({"action": "assertVisible", "target": assertion})

    if len(steps) < 2:
        return None, destructive_cases

    priority = "critical" if _flow_has_interaction(flow) else "high"
    feature = _flow_feature_name(flow)
    safe_case = {
        "name": _flow_scenario_name(flow, indices),
        "feature": feature,
        "priority": priority,
        "flow_id": flow.get("flow_id"),
        "destructive": False,
        "execution_order": "default",
        "tags": ["@flow-replay"],
        "steps": steps,
    }
    return safe_case, destructive_cases


def template_page_smoke(page: dict[str, Any], indices: dict[str, Any]) -> dict[str, Any] | None:
    """One high-priority smoke scenario per crawled page."""
    page_id = str(page.get("page_id") or "")
    page_url = (page.get("url") or "").strip()
    if not page_url:
        return None

    assertion = _pick_assertion_target(indices["by_page"].get(page_id, []))
    if not assertion:
        return None

    label = _page_label(page, page_url)
    module = label.split()[0] if label else "App"
    return {
        "name": f"Verify {label} page loads and key content is visible",
        "feature": f"{module} pages",
        "priority": "high",
        "flow_id": None,
        "destructive": False,
        "execution_order": "default",
        "tags": ["@smoke", "@page"],
        "steps": [
            {"action": "navigate", "target": page_url},
            {"action": "assertVisible", "target": assertion},
        ],
    }


def template_navigation(
    page: dict[str, Any], indices: dict[str, Any], *, max_links: int = 2
) -> list[dict[str, Any]]:
    """Click non-destructive navigation links discovered on a page."""
    page_id = str(page.get("page_id") or "")
    page_url = (page.get("url") or "").strip()
    if not page_url:
        return []

    cases: list[dict[str, Any]] = []
    links = [
        element
        for element in indices["by_page"].get(page_id, [])
        if element.get("role") == "link" or (element.get("tag_name") or "").lower() == "a"
    ]
    safe_links = [element for element in links if not _is_destructive_text(element.get("text_content"))]
    for element in safe_links[:max_links]:
        click_target = _element_target(element)
        if not click_target:
            continue
        label = (element.get("text_content") or "link").strip()[:60]
        cases.append(
            {
                "name": f"From {_page_label(page, page_url)}: click the \"{label}\" link",
                "feature": f"{_page_label(page, page_url)} navigation",
                "priority": "medium",
                "flow_id": None,
                "destructive": False,
                "execution_order": "default",
                "tags": ["@navigation"],
                "steps": [
                    {"action": "navigate", "target": page_url},
                    {"action": "click", "target": click_target},
                ],
            }
        )
    return cases


def template_destructive_actions(
    page: dict[str, Any],
    indices: dict[str, Any],
    *,
    max_actions: int = 2,
) -> list[dict[str, Any]]:
    """Generate logout/delete/destructive click tests — scheduled to run last."""
    page_id = str(page.get("page_id") or "")
    page_url = (page.get("url") or "").strip()
    if not page_url:
        return []

    cases: list[dict[str, Any]] = []
    candidates = [
        element
        for element in indices["by_page"].get(page_id, [])
        if _is_destructive_text(element.get("text_content"))
        and (
            element.get("role") in {"button", "link", "menuitem"}
            or (element.get("tag_name") or "").lower() in {"button", "a"}
        )
    ]
    for element in candidates[:max_actions]:
        click_target = _element_target(element)
        if not click_target:
            continue
        label = (element.get("text_content") or "destructive action").strip()[:60]
        cases.append(
            _destructive_case(
                name=f"Destructive action — {label}",
                steps=[
                    {"action": "navigate", "target": page_url},
                    {"action": "click", "target": click_target},
                ],
            )
        )
    return cases


def template_form_interaction(page: dict[str, Any], indices: dict[str, Any]) -> dict[str, Any] | None:
    """Fill a text field and click a non-destructive button on pages with inputs."""
    page_id = str(page.get("page_id") or "")
    page_url = (page.get("url") or "").strip()
    if not page_url:
        return None

    elements = indices["by_page"].get(page_id, [])
    textbox = next(
        (
            element
            for element in elements
            if element.get("role") in {"textbox", "combobox"}
            or (element.get("tag_name") or "").lower() in {"input", "textarea"}
        ),
        None,
    )
    button = next(
        (
            element
            for element in elements
            if (element.get("role") == "button" or (element.get("tag_name") or "").lower() == "button")
            and not _is_destructive_text(element.get("text_content"))
        ),
        None,
    )
    if textbox is None or button is None:
        return None

    fill_target = _element_target(textbox)
    click_target = _element_target(button)
    if not fill_target or not click_target:
        return None

    page_title = _page_label(page, page_url)
    return {
        "name": f"From {page_title}: fill a sample field and submit",
        "feature": f"{page_title} forms",
        "priority": "medium",
        "flow_id": None,
        "destructive": False,
        "execution_order": "default",
        "tags": ["@form"],
        "steps": [
            {"action": "navigate", "target": page_url},
            {"action": "fill", "target": fill_target},
            {"action": "click", "target": click_target},
        ],
    }


def _dedupe_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for case in cases:
        key = _case_dedupe_key(case)
        if key in seen:
            continue
        seen.add(key)
        unique.append(case)
    return unique


def _filter_safe_cases(
    cases: list[dict[str, Any]],
    *,
    priorities: list[str],
    max_tests: int,
) -> list[dict[str, Any]]:
    allowed = set(priorities)
    filtered = [case for case in cases if case.get("priority") in allowed]
    filtered.sort(key=lambda item: PRIORITY_RANK.get(str(item.get("priority")), 99))
    return filtered[:max_tests]


def _finalize_test_suite(
    safe_cases: list[dict[str, Any]],
    destructive_cases: list[dict[str, Any]],
    *,
    priorities: list[str],
    max_tests: int,
) -> list[dict[str, Any]]:
    """Return safe tests first, destructive tests always appended at the end."""
    safe_selected = _filter_safe_cases(
        _dedupe_cases(safe_cases), priorities=priorities, max_tests=max_tests
    )
    destructive_selected = _dedupe_cases(destructive_cases)[:MAX_DESTRUCTIVE_CASES]
    return safe_selected + destructive_selected


def generate_cases_from_recommended_areas(
    appmap: dict[str, Any],
    *,
    max_tests: int = 10,
    priorities: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Build grounded cases from AppMap recommended_test_areas (Phase D handoff)."""
    areas = list(appmap.get("recommended_test_areas") or [])
    if not areas:
        return []

    selected_priorities = priorities or ["critical", "high", "medium"]
    indices = _build_indices(appmap)
    pages_by_id = indices["pages_by_id"]
    forms_by_id = {
        str(form.get("form_id") or ""): form for form in (appmap.get("forms") or []) if form.get("form_id")
    }
    catalog_by_target = {
        f"{entry.get('target_type')}:{entry.get('target_id')}": entry
        for entry in (appmap.get("test_data_catalog") or [])
        if entry.get("target_type") and entry.get("target_id")
    }
    mappings_by_form = {
        str(mapping.get("form_id") or ""): mapping
        for mapping in (appmap.get("api_ui_mappings") or [])
        if mapping.get("form_id") and float(mapping.get("confidence") or 0) >= 0.7
    }

    cases: list[dict[str, Any]] = []
    for area in sorted(areas, key=lambda item: float(item.get("priority_index") or 0), reverse=True):
        priority = str(area.get("priority") or "medium")
        if priority not in selected_priorities:
            continue
        area_type = str(area.get("area_type") or "")
        form_id = str(area.get("form_id") or "")
        page_id = str(area.get("page_id") or "")
        page = pages_by_id.get(page_id) or {}
        page_url = str(page.get("url") or "").strip()
        if not page_url and area_type != "auth_flow":
            continue

        if area_type == "form_validation" and form_id:
            form = forms_by_id.get(form_id) or {}
            field_ids = [str(item) for item in (form.get("field_element_ids") or [])]
            steps: list[dict[str, str]] = [{"action": "navigate", "target": page_url}]
            catalog = catalog_by_target.get(f"form:{form_id}") or {}
            replay_steps = list(catalog.get("replay_steps") or [])
            for replay_step in replay_steps:
                target = _step_target(replay_step)
                if not target:
                    continue
                action = str(replay_step.get("action") or "click")
                step: dict[str, str] = {"action": action, "target": target}
                if replay_step.get("value"):
                    step["value"] = str(replay_step["value"])
                steps.append(step)
            values_by_name = {
                str(field.get("name") or "").lower(): str(field.get("suggested_safe_value") or "")
                for field in (catalog.get("fields") or [])
            }
            for field_id in field_ids[:4]:
                element = next(
                    (item for item in indices["by_page"].get(page_id, []) if str(item.get("element_id")) == field_id),
                    None,
                )
                if element is None:
                    continue
                target = _element_target(element)
                if not target:
                    continue
                attrs = dict(element.get("attributes") or {})
                name = str(attrs.get("name") or element.get("text_content") or "").lower()
                value = values_by_name.get(name, "qa-sample-value")
                steps.append({"action": "fill", "target": target, "value": value})
            submit = next(
                (
                    element
                    for element in indices["by_page"].get(page_id, [])
                    if (element.get("role") == "button" or (element.get("tag_name") or "").lower() == "button")
                    and not _is_destructive_text(element.get("text_content"))
                ),
                None,
            )
            submit_target = _element_target(submit) if submit else None
            if submit_target:
                steps.append({"action": "click", "target": submit_target})
            if len(steps) >= 2:
                cases.append(
                    {
                        "name": str(area.get("area") or "Form validation"),
                        "feature": f"{page.get('title') or 'Form'} validation",
                        "priority": priority,
                        "flow_id": None,
                        "destructive": False,
                        "execution_order": "default",
                        "tags": ["@recommended-area", "@form"],
                        "recommended_area_id": area.get("area_id"),
                        "steps": steps,
                    }
                )
            mapping = mappings_by_form.get(form_id)
            if mapping and len(steps) >= 2:
                endpoint_id = str(mapping.get("api_endpoint_id") or "")
                endpoint = next(
                    (
                        item
                        for item in (appmap.get("api_endpoints") or [])
                        if str(item.get("endpoint_id") or "") == endpoint_id
                    ),
                    None,
                )
                if endpoint:
                    method = str(endpoint.get("method") or "POST").upper()
                    path = str(endpoint.get("path_pattern") or endpoint.get("path") or "")
                    cases.append(
                        {
                            "name": f"{area.get('area')} — paired API ({method} {path})",
                            "feature": "API/UI paired validation",
                            "priority": priority,
                            "flow_id": None,
                            "destructive": False,
                            "execution_order": "default",
                            "tags": ["@recommended-area", "@api-ui-pair"],
                            "recommended_area_id": area.get("area_id"),
                            "steps": steps,
                        }
                    )
            continue

        if area_type == "destructive_control":
            element_id = str(area.get("element_id") or "")
            element = next(
                (
                    item
                    for item in indices["by_page"].get(page_id, [])
                    if str(item.get("element_id") or "") == element_id
                ),
                None,
            )
            target = _element_target(element) if element else None
            if target:
                cases.append(
                    _destructive_case(
                        name=str(area.get("area") or "Destructive control"),
                        steps=[
                            {"action": "navigate", "target": page_url},
                            {"action": "click", "target": target},
                        ],
                    )
                )
            continue

        if area_type == "api_contract":
            endpoint_id = str(area.get("api_endpoint_id") or "")
            endpoint = next(
                (
                    item
                    for item in (appmap.get("api_endpoints") or [])
                    if str(item.get("endpoint_id") or "") == endpoint_id
                ),
                None,
            )
            if endpoint and page_url:
                method = str(endpoint.get("method") or "POST").upper()
                path = str(endpoint.get("path_pattern") or endpoint.get("path") or "")
                cases.append(
                    {
                        "name": str(area.get("area") or f"API contract {method} {path}"),
                        "feature": "API contract validation",
                        "priority": priority,
                        "flow_id": None,
                        "destructive": False,
                        "execution_order": "default",
                        "tags": ["@recommended-area", "@api-contract"],
                        "recommended_area_id": area.get("area_id"),
                        "steps": [
                            {"action": "navigate", "target": page_url},
                            {
                                "action": "assertVisible",
                                "target": _pick_assertion_target(indices["by_page"].get(page_id, []))
                                or page_url,
                            },
                        ],
                    }
                )

    return _dedupe_cases(cases)[:max_tests]


def generate_test_cases(
    appmap: dict[str, Any],
    *,
    max_tests: int = 200,
    priorities: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Generate rule-based test cases from any AppMap document."""
    if not appmap:
        return []

    selected_priorities = priorities or ["critical", "high", "medium"]
    indices = _build_indices(appmap)
    safe_cases: list[dict[str, Any]] = []
    destructive_cases: list[dict[str, Any]] = []

    safe_cases.extend(
        generate_cases_from_recommended_areas(
            appmap,
            max_tests=max_tests,
            priorities=selected_priorities,
        )
    )

    for flow in appmap.get("flows") or []:
        safe_case, flow_destructive = template_flow_replay(flow, indices)
        if safe_case is not None:
            safe_cases.append(safe_case)
        destructive_cases.extend(flow_destructive)

    for page in appmap.get("pages") or []:
        smoke = template_page_smoke(page, indices)
        if smoke is not None:
            safe_cases.append(smoke)
        safe_cases.extend(template_navigation(page, indices))
        destructive_cases.extend(template_destructive_actions(page, indices))
        form_case = template_form_interaction(page, indices)
        if form_case is not None:
            safe_cases.append(form_case)

    return _finalize_test_suite(
        safe_cases,
        destructive_cases,
        priorities=selected_priorities,
        max_tests=max_tests,
    )
