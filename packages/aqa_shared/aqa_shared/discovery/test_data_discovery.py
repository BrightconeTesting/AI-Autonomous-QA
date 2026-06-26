"""Test data catalog builder (DISCOVERY-AGENT-VISION-SPEC §8.10)."""

from __future__ import annotations

import re
import uuid
from typing import Any

PII_CLASSES = {
    "email": "email",
    "phone": "phone",
    "password": "password",
    "ssn": "ssn",
    "card": "payment",
    "credit": "payment",
    "cvv": "payment",
}

_SEMANTIC_NAME_PATTERNS = (
    re.compile(r'getByPlaceholder\("([^"]+)"'),
    re.compile(r"getByPlaceholder\('([^']+)'"),
    re.compile(r'getByLabel\("([^"]+)"'),
    re.compile(r"getByLabel\('([^']+)'"),
    re.compile(r'getByRole\([^,]+,\s*\{\s*name:\s*"([^"]+)"'),
    re.compile(r"getByRole\([^,]+,\s*\{\s*name:\s*'([^']+)'"),
)


def _pii_class(field_name: str, data_type: str) -> str | None:
    blob = f"{field_name} {data_type}".lower()
    for keyword, label in PII_CLASSES.items():
        if keyword in blob:
            return label
    return None


def _slugify_field_name(raw: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", raw.strip().lower())
    cleaned = re.sub(r"[\s_-]+", "_", cleaned).strip("_")
    return cleaned[:64] or "field"


def _name_from_semantic_selector(selector: str) -> str | None:
    for pattern in _SEMANTIC_NAME_PATTERNS:
        match = pattern.search(selector)
        if not match:
            continue
        label = match.group(1).strip()
        if not label:
            continue
        # Combobox labels often list all options — keep the first meaningful token group.
        if len(label) > 48 and " " in label:
            return label.split("  ")[0].strip() or label[:48]
        return label
    return None


def _clean_display_label(raw: str) -> str:
    text = re.sub(r"\s+", " ", raw.strip())
    text = re.sub(r"\s*\*\s*$", "", text)
    return text[:120]


def _resolve_display_name(element: dict[str, Any]) -> str | None:
    """Human-readable field label for UI (e.g. 'Manufacturer', 'Parent / Owner')."""
    attrs = dict(element.get("attributes") or {})
    for candidate in (
        attrs.get("label"),
        attrs.get("aria-label"),
        attrs.get("accessible_name"),
    ):
        text = _clean_display_label(str(candidate or ""))
        if text and not _looks_like_placeholder_hint(text):
            return text

    selector = str(element.get("semantic_selector") or "")
    for pattern in _SEMANTIC_NAME_PATTERNS:
        if "Label" not in pattern.pattern:
            continue
        match = pattern.search(selector)
        if match:
            text = _clean_display_label(match.group(1))
            if text:
                return text

    parsed = _name_from_semantic_selector(selector)
    if parsed and not _looks_like_placeholder_hint(parsed):
        return _clean_display_label(parsed.replace("_", " "))

    for candidate in (attrs.get("name"), attrs.get("id")):
        text = _clean_display_label(str(candidate or ""))
        if text:
            return text

    return None


def _looks_like_placeholder_hint(text: str) -> bool:
    lowered = text.lower().strip()
    if lowered.startswith(("e.g.", "eg.", "ex.", "https://", "http://", "1-800")):
        return True
    if lowered in {"—", "-", "..."}:
        return True
    return False


def _resolve_field_name(element: dict[str, Any]) -> str | None:
    """Derive a stable catalog field key from element metadata."""
    display = _resolve_display_name(element)
    if display:
        return _slugify_field_name(display)

    attrs = dict(element.get("attributes") or {})
    html5 = dict(attrs.get("html5") or {})
    for candidate in (
        attrs.get("name"),
        attrs.get("id"),
        attrs.get("placeholder"),
    ):
        text = str(candidate or "").strip()
        if text:
            return _slugify_field_name(text)

    selector = str(element.get("semantic_selector") or "")
    parsed = _name_from_semantic_selector(selector)
    if parsed:
        return _slugify_field_name(parsed)

    xpath = str(element.get("xpath_fallback") or "").strip()
    if xpath:
        digest = re.sub(r"[^a-z0-9]", "", xpath.lower())[-12:]
        return f"field_{digest or 'unknown'}"

    input_type = str(html5.get("type") or attrs.get("type") or "").lower()
    if input_type and input_type not in {"text", "search"}:
        return f"field_{_slugify_field_name(input_type)}"

    role = str(element.get("role") or "").lower()
    tag = str(element.get("tag_name") or "").lower()
    if tag:
        return _slugify_field_name(f"{tag}_{role}" if role else tag)

    return None


def _infer_data_type(element: dict[str, Any], attrs: dict[str, Any], html5: dict[str, Any]) -> str:
    explicit = str(html5.get("type") or attrs.get("type") or "").lower()
    if explicit:
        return explicit
    role = str(element.get("role") or "").lower()
    tag = str(element.get("tag_name") or "").lower()
    if role == "combobox" or tag == "select":
        return "select"
    if role == "checkbox" or explicit == "checkbox":
        return "checkbox"
    if role == "radio" or explicit == "radio":
        return "radio"
    if tag == "textarea" or role == "textbox":
        return "text"
    return "text"


def _is_fillable_form_field(element: dict[str, Any]) -> bool:
    tag = str(element.get("tag_name") or "").lower()
    role = str(element.get("role") or "").lower()
    attrs = dict(element.get("attributes") or {})
    input_type = str(attrs.get("type") or "").lower()
    if tag == "button" or role == "button":
        return False
    if tag == "input" and input_type in {"submit", "button", "reset", "hidden", "file", "image"}:
        return False
    return tag in {"input", "textarea", "select"} or role in {
        "textbox",
        "combobox",
        "checkbox",
        "radio",
    }


def _suggested_safe_value(
    *,
    field_name: str,
    data_type: str,
    run_token: str,
    constraints: dict[str, Any],
) -> str:
    lowered = field_name.lower()
    if data_type == "password" or "password" in lowered:
        return "***"
    if data_type == "email" or "email" in lowered:
        return f"qa-test-{run_token}@example.com"
    if data_type == "tel" or "phone" in lowered:
        return "5550100199"
    if data_type in {"number", "integer"}:
        return str(constraints.get("min") or "1")
    if data_type == "date":
        return "2026-01-15"
    if data_type == "url":
        return f"https://example.com/qa-{run_token}"
    if data_type in {"checkbox", "radio", "select"}:
        return "first_option"
    return f"qa-{run_token}-{lowered[:24] or 'value'}"


def _field_from_element(element: dict[str, Any], *, run_token: str) -> dict[str, Any] | None:
    if not _is_fillable_form_field(element):
        return None

    attrs = dict(element.get("attributes") or {})
    html5 = dict(attrs.get("html5") or {})
    name = _resolve_field_name(element)
    if not name:
        return None

    display_name = _resolve_display_name(element) or name.replace("_", " ").title()
    data_type = _infer_data_type(element, attrs, html5)
    constraints: dict[str, Any] = {}
    for key in ("required", "pattern", "min", "max", "minlength", "maxlength"):
        if key in html5:
            constraints[key] = html5[key]
        elif attrs.get(key) is not None:
            constraints[key] = attrs.get(key)
    required = bool(constraints.get("required") or attrs.get("required"))
    filled_during_crawl = bool(attrs.get("filled_during_crawl"))

    field: dict[str, Any] = {
        "name": name,
        "display_name": display_name,
        "data_type": data_type,
        "required": required,
        "constraints": constraints,
        "suggested_safe_value": _suggested_safe_value(
            field_name=display_name,
            data_type=data_type,
            run_token=run_token,
            constraints=constraints,
        ),
        "pii_class": _pii_class(display_name, data_type),
        "element_id": str(element.get("element_id") or "") or None,
        "semantic_selector": element.get("semantic_selector"),
        "filled_during_crawl": filled_during_crawl,
        "needs_test_data": not filled_during_crawl,
    }
    return field


def _dedupe_field_names(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, int] = {}
    output: list[dict[str, Any]] = []
    for field in fields:
        base = str(field.get("name") or "field")
        count = seen.get(base, 0)
        if count:
            field = dict(field)
            field["name"] = f"{base}_{count + 1}"
        seen[base] = count + 1
        output.append(field)
    return output


def _replay_step_from_trigger(trigger: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": trigger.get("action_type") or "click",
        "semantic_selector": trigger.get("semantic_selector"),
        "text_content": trigger.get("text_content"),
        "role": trigger.get("role"),
        "value": trigger.get("value"),
    }


def build_replay_steps_for_state(
    state_key: str | None,
    states_by_key: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build ordered replay steps from baseline to a target state."""
    if not state_key:
        return []

    path: list[dict[str, Any]] = []
    current_key: str | None = state_key
    while current_key:
        state = states_by_key.get(current_key)
        if not state:
            break
        parent_key = state.get("parent_state_key")
        if not parent_key:
            break
        trigger = dict(state.get("trigger_action") or {})
        if trigger:
            path.append(_replay_step_from_trigger(trigger))
        current_key = str(parent_key) if parent_key else None

    path.reverse()
    return path


def _context_label_for_form(
    form: dict[str, Any],
    *,
    state_key: str | None,
    states_by_key: dict[str, dict[str, Any]],
) -> str | None:
    attrs = dict(form.get("attributes") or {})
    if attrs.get("overlay_type"):
        return str(form.get("name") or attrs.get("overlay_type"))
    if state_key:
        state = states_by_key.get(state_key) or {}
        trigger = dict(state.get("trigger_action") or {})
        label = (trigger.get("text_content") or state.get("title") or "").strip()
        if label:
            return label[:120]
    return str(form.get("name") or "") or None


_GENERIC_FORM_NAME = re.compile(r"^form\s*\d*$", re.IGNORECASE)


def form_field_signature(fields: list[dict[str, Any]]) -> tuple[tuple[str, str], ...]:
    """Stable identity for a form surface from normalized field keys and types."""
    parts = sorted(
        (str(field.get("name") or ""), str(field.get("data_type") or "text"))
        for field in fields
        if field.get("name")
    )
    return tuple(parts)


def _state_opened_via_interaction(
    state_key: str | None,
    states_by_key: dict[str, dict[str, Any]],
) -> bool:
    if not state_key:
        return False
    state = states_by_key.get(state_key) or {}
    trigger = dict(state.get("trigger_action") or {})
    return bool(
        (trigger.get("text_content") or "").strip()
        or trigger.get("semantic_selector")
        or trigger.get("interaction_key")
    )


def _form_surface_title(form: dict[str, Any], context_label: str | None) -> str | None:
    attrs = dict(form.get("attributes") or {})
    for candidate in (
        str(form.get("name") or ""),
        str(attrs.get("name") or ""),
        context_label or "",
    ):
        text = _clean_display_label(candidate)
        if text and not _GENERIC_FORM_NAME.match(text):
            return text
    return None


def _catalog_candidate_score(
    *,
    form: dict[str, Any],
    fields: list[dict[str, Any]],
    state_key: str | None,
    states_by_key: dict[str, dict[str, Any]],
    context_label: str | None,
) -> int:
    score = 0
    if _state_opened_via_interaction(state_key, states_by_key):
        score += 100
    elif state_key:
        score += 20

    if _form_surface_title(form, context_label):
        score += 40

    if context_label and not _GENERIC_FORM_NAME.match(context_label.strip()):
        score += 25

    if attrs := dict(form.get("attributes") or {}):
        if attrs.get("overlay_type"):
            score += 15

    filled = sum(1 for field in fields if field.get("filled_during_crawl"))
    score += min(filled * 4, 20)

    if state_key:
        replay_len = 0
        current_key: str | None = state_key
        while current_key:
            state = states_by_key.get(current_key) or {}
            parent_key = state.get("parent_state_key")
            if not parent_key:
                break
            replay_len += 1
            current_key = str(parent_key)
        score += min(replay_len * 3, 15)

    return score


def _pick_best_context_label(
    *,
    form: dict[str, Any],
    primary_label: str | None,
    reachable_via: list[str],
) -> str | None:
    surface = _form_surface_title(form, primary_label)
    if surface:
        return surface
    for label in [primary_label, *reachable_via]:
        text = _clean_display_label(str(label or ""))
        if text and not _GENERIC_FORM_NAME.match(text):
            return text
    return primary_label or str(form.get("name") or "") or None


def _merge_duplicate_form_catalog_entries(
    entries: list[dict[str, Any]],
    *,
    forms_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Collapse per-state crawl snapshots that describe the same form surface."""
    buckets: dict[tuple[str, tuple[tuple[str, str], ...]], list[dict[str, Any]]] = {}

    for entry in entries:
        if entry.get("target_type") != "form":
            buckets.setdefault(("__passthrough__", ()), []).append(entry)
            continue
        form = forms_by_id.get(str(entry.get("target_id") or ""), {})
        page_id = str(form.get("page_id") or "")
        signature = form_field_signature(list(entry.get("fields") or []))
        if not signature:
            continue
        buckets.setdefault((page_id, signature), []).append(entry)

    merged: list[dict[str, Any]] = []
    passthrough = buckets.pop(("__passthrough__", ()), [])
    merged.extend(passthrough)

    for (_page_id, _signature), group in buckets.items():
        if len(group) == 1:
            merged.append(group[0])
            continue

        ranked = sorted(
            group,
            key=lambda item: int(item.get("_dedupe_score") or 0),
            reverse=True,
        )
        winner = dict(ranked[0])
        winner.pop("_dedupe_score", None)

        reachable: list[str] = []
        alias_ids: list[str] = []
        winner_label = str(winner.get("context_label") or "")
        winner_form = forms_by_id.get(str(winner.get("target_id") or ""), {})

        for loser in ranked[1:]:
            loser_id = str(loser.get("target_id") or "")
            if loser_id and loser_id != winner.get("target_id"):
                alias_ids.append(loser_id)
            label = str(loser.get("context_label") or "").strip()
            if label and label != winner_label and label not in reachable:
                reachable.append(label)

        if reachable:
            winner["reachable_via"] = reachable
        if alias_ids:
            winner["alias_target_ids"] = alias_ids

        winner["context_label"] = _pick_best_context_label(
            form=winner_form,
            primary_label=winner.get("context_label"),
            reachable_via=reachable,
        )
        merged.append(winner)

    return merged


def _fields_for_form(
    form: dict[str, Any],
    *,
    elements_by_id: dict[str, dict[str, Any]],
    run_token: str,
) -> list[dict[str, Any]]:
    field_ids = [str(item) for item in (form.get("field_element_ids") or [])]
    fields: list[dict[str, Any]] = []
    for field_id in field_ids:
        element = elements_by_id.get(field_id)
        if element is None:
            continue
        field = _field_from_element(element, run_token=run_token)
        if field:
            fields.append(field)
    return _dedupe_field_names(fields)


def form_signature_from_field_elements(
    form: dict[str, Any],
    *,
    elements_by_id: dict[str, dict[str, Any]],
) -> tuple[tuple[str, str], ...]:
    """Field-surface signature for a persisted form row (no synthetic values)."""
    fields: list[dict[str, Any]] = []
    for field_id in form.get("field_element_ids") or []:
        element = elements_by_id.get(str(field_id))
        if element is None:
            continue
        name = _resolve_field_name(element)
        if not name:
            continue
        attrs = dict(element.get("attributes") or {})
        html5 = dict(attrs.get("html5") or {})
        data_type = _infer_data_type(element, attrs, html5)
        fields.append({"name": name, "data_type": data_type})
    return form_field_signature(fields)


def canonicalize_forms(
    forms: list[dict[str, Any]],
    *,
    elements: list[dict[str, Any]],
    states: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Pick one form record per unique field surface on each page."""
    elements_by_id = {str(element.get("element_id") or ""): element for element in elements}
    states_by_key = {
        str(state.get("state_key") or ""): state for state in (states or []) if state.get("state_key")
    }
    state_id_to_key = {
        str(state.get("state_id") or ""): str(state.get("state_key") or "")
        for state in (states or [])
        if state.get("state_id") and state.get("state_key")
    }
    buckets: dict[tuple[str, tuple[tuple[str, str], ...]], list[tuple[dict[str, Any], int]]] = {}

    for form in forms:
        signature = form_signature_from_field_elements(form, elements_by_id=elements_by_id)
        if not signature:
            continue
        page_id = str(form.get("page_id") or "")
        state_key: str | None = None
        raw_state_id = form.get("state_id")
        if raw_state_id:
            state_key = state_id_to_key.get(str(raw_state_id))
        context_label = _context_label_for_form(form, state_key=state_key, states_by_key=states_by_key)
        fields = _fields_for_form(form, elements_by_id=elements_by_id, run_token="canonical")
        score = _catalog_candidate_score(
            form=form,
            fields=fields,
            state_key=state_key,
            states_by_key=states_by_key,
            context_label=context_label,
        )
        key = (page_id, signature)
        buckets.setdefault(key, []).append((form, score))

    winners: list[dict[str, Any]] = []
    for group in buckets.values():
        winners.append(max(group, key=lambda item: item[1])[0])
    return winners


def build_test_data_catalog(
    *,
    forms: list[dict[str, Any]],
    elements: list[dict[str, Any]],
    api_endpoints: list[dict[str, Any]],
    data_entities: list[dict[str, Any]] | None = None,
    states: list[dict[str, Any]] | None = None,
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    """Infer synthetic-safe test data fixtures from forms, fields, and API schemas."""
    run_token = re.sub(r"[^a-zA-Z0-9_-]", "", str(run_id or uuid.uuid4()))[:12]
    elements_by_id = {str(element.get("element_id") or ""): element for element in elements}
    states_by_key = {
        str(state.get("state_key") or ""): state for state in (states or []) if state.get("state_key")
    }
    state_id_to_key = {
        str(state.get("state_id") or ""): str(state.get("state_key") or "")
        for state in (states or [])
        if state.get("state_id") and state.get("state_key")
    }
    catalog: list[dict[str, Any]] = []
    form_entries: list[dict[str, Any]] = []
    forms_by_id = {str(form.get("form_id") or ""): form for form in forms if form.get("form_id")}

    for form in forms:
        fields = _fields_for_form(form, elements_by_id=elements_by_id, run_token=run_token)
        if not fields:
            continue

        state_key: str | None = None
        raw_state_id = form.get("state_id")
        if raw_state_id:
            state_key = state_id_to_key.get(str(raw_state_id))

        unfilled_count = sum(1 for field in fields if field.get("needs_test_data"))
        context_label = _context_label_for_form(form, state_key=state_key, states_by_key=states_by_key)
        entry: dict[str, Any] = {
            "catalog_id": str(uuid.uuid4()),
            "target_type": "form",
            "target_id": str(form.get("form_id") or ""),
            "fields": fields,
            "synthetic_strategy": "deterministic_fixture",
            "never_use_live_pii": True,
            "unfilled_field_count": unfilled_count,
            "filled_during_crawl": unfilled_count == 0 and bool(fields),
            "_dedupe_score": _catalog_candidate_score(
                form=form,
                fields=fields,
                state_key=state_key,
                states_by_key=states_by_key,
                context_label=context_label,
            ),
        }
        if state_key:
            entry["state_key"] = state_key
            entry["replay_steps"] = build_replay_steps_for_state(state_key, states_by_key)
        if context_label:
            entry["context_label"] = context_label
        form_entries.append(entry)

    catalog.extend(_merge_duplicate_form_catalog_entries(form_entries, forms_by_id=forms_by_id))

    for endpoint in api_endpoints:
        schema = endpoint.get("request_schema") or {}
        props: dict[str, Any] = {}
        if isinstance(schema, dict):
            content = schema.get("content") if "content" in schema else schema
            if isinstance(content, dict):
                for media in content.values():
                    if isinstance(media, dict):
                        props.update((media.get("schema") or {}).get("properties") or {})
        for key in endpoint.get("body_keys") or []:
            props.setdefault(str(key), {"type": "string"})
        if not props:
            continue
        fields = []
        for name, definition in props.items():
            data_type = str((definition or {}).get("type") or "string")
            fields.append(
                {
                    "name": str(name),
                    "data_type": data_type,
                    "required": str(name) in ((definition or {}).get("required") or []),
                    "constraints": {},
                    "suggested_safe_value": _suggested_safe_value(
                        field_name=str(name),
                        data_type=data_type,
                        run_token=run_token,
                        constraints={},
                    ),
                    "pii_class": _pii_class(str(name), data_type),
                    "needs_test_data": True,
                }
            )
        if fields:
            catalog.append(
                {
                    "catalog_id": str(uuid.uuid4()),
                    "target_type": "api_endpoint",
                    "target_id": str(endpoint.get("endpoint_id") or ""),
                    "fields": fields,
                    "synthetic_strategy": "deterministic_fixture",
                    "never_use_live_pii": True,
                }
            )

    for entity in data_entities or []:
        entity_fields = [str(name) for name in (entity.get("fields") or [])]
        if not entity_fields:
            continue
        catalog.append(
            {
                "catalog_id": str(uuid.uuid4()),
                "target_type": "entity",
                "target_id": str(entity.get("entity_id") or ""),
                "fields": [
                    {
                        "name": name,
                        "data_type": "string",
                        "required": False,
                        "constraints": {},
                        "suggested_safe_value": _suggested_safe_value(
                            field_name=name,
                            data_type="string",
                            run_token=run_token,
                            constraints={},
                        ),
                        "pii_class": _pii_class(name, "string"),
                        "needs_test_data": True,
                    }
                    for name in entity_fields
                ],
                "synthetic_strategy": "deterministic_fixture",
                "never_use_live_pii": True,
            }
        )

    return catalog
