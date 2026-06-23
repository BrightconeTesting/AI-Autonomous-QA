"""API ↔ UI correlation (DISCOVERY-AGENT-VISION-SPEC §9.3)."""

from __future__ import annotations

import json
from typing import Any

CIC_WINDOW_MS = 2000.0
REVIEW_THRESHOLD = 0.6


def _clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, round(value, 3)))


def _body_keys_from_hash_or_schema(endpoint: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    schema = endpoint.get("request_schema") or {}
    if isinstance(schema, dict):
        content = schema.get("content") if "content" in schema else schema
        if isinstance(content, dict):
            for media in content.values():
                if not isinstance(media, dict):
                    continue
                props = (media.get("schema") or {}).get("properties") or {}
                if isinstance(props, dict):
                    keys.update(str(key).lower() for key in props.keys())
    body_keys = endpoint.get("body_keys") or []
    keys.update(str(key).lower() for key in body_keys)
    return keys


def _form_field_names(form: dict[str, Any], elements: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    attrs = form.get("attributes") or {}
    if attrs.get("name"):
        names.add(str(attrs["name"]).lower())
    if attrs.get("form_key"):
        names.add(str(attrs["form_key"]).lower())
    form_id = str(form.get("form_id") or "")
    for element in elements:
        if str(element.get("form_id") or element.get("attributes", {}).get("form_key") or "") not in {
            form_id,
            str(attrs.get("form_key") or ""),
        }:
            continue
        for key in ("name", "text_content"):
            value = element.get(key) or (element.get("attributes") or {}).get(key)
            if value:
                names.add(str(value).lower())
    return names


def correlate_cic_interactions(
    *,
    page_id: str,
    interaction_events: list[dict[str, Any]],
    network_events: list[dict[str, Any]],
    forms: list[dict[str, Any]],
    elements: list[dict[str, Any]],
    endpoint_by_pattern: dict[str, dict[str, Any]],
    window_ms: float = CIC_WINDOW_MS,
) -> list[dict[str, Any]]:
    """Map CIC interactions to network requests in a time window."""
    mappings: list[dict[str, Any]] = []
    forms_by_key = {
        str((form.get("attributes") or {}).get("form_key") or form.get("form_id") or ""): form
        for form in forms
    }

    for event in interaction_events:
        started = float(event.get("timestamp_ms") or 0)
        trigger = dict(event.get("trigger_action") or {})
        form_key = str(event.get("form_key") or trigger.get("form_key") or "")
        form = forms_by_key.get(form_key) if form_key else None
        element_key = str(event.get("interaction_key") or trigger.get("interaction_key") or "")

        for network in network_events:
            observed = float(network.get("timestamp_ms") or 0)
            delta = observed - started
            if delta < 0 or delta > window_ms:
                continue

            pattern = str(network.get("path_pattern") or "")
            endpoint = endpoint_by_pattern.get(f"{str(network.get('method') or 'GET').upper()} {pattern}")
            if endpoint is None:
                continue

            proximity = 1.0 - (delta / window_ms)
            confidence = _clamp_confidence(0.7 + 0.3 * proximity)
            method = "cic_interaction_window"
            form_id = str(form.get("form_id")) if form and form.get("form_id") else None

            body_keys = set(str(key).lower() for key in (network.get("body_keys") or []))
            if form and body_keys:
                field_names = _form_field_names(form, elements)
                overlap = body_keys & field_names
                if overlap:
                    confidence = _clamp_confidence(confidence + 0.1)
                    method = "form_body_field_match"

            mappings.append(
                {
                    "api_endpoint_id": str(endpoint.get("endpoint_id") or ""),
                    "page_id": page_id,
                    "form_id": form_id,
                    "element_id": str(event.get("element_id") or "") or None,
                    "flow_id": None,
                    "trigger_action": trigger,
                    "confidence": confidence,
                    "correlation_method": method,
                    "review_required": confidence < REVIEW_THRESHOLD,
                }
            )
    return mappings


def correlate_form_endpoints(
    *,
    page_id: str,
    forms: list[dict[str, Any]],
    api_endpoints: list[dict[str, Any]],
    elements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Map mutating forms to API endpoints observed on the same page."""
    mappings: list[dict[str, Any]] = []
    page_endpoints = [
        endpoint
        for endpoint in api_endpoints
        if page_id in [str(item) for item in (endpoint.get("seen_on_page_ids") or [])]
        or str(endpoint.get("first_seen_page_id") or "") == page_id
    ]
    mutating_methods = {"POST", "PUT", "PATCH", "DELETE"}

    for form in forms:
        if str(form.get("page_id") or "") != page_id:
            continue
        form_method = str(form.get("method") or "get").upper()
        if form_method == "GET":
            continue

        candidates = [
            endpoint
            for endpoint in page_endpoints
            if str(endpoint.get("method") or "").upper() in mutating_methods
        ]
        if not candidates:
            continue

        field_names = _form_field_names(form, elements)
        for endpoint in candidates:
            body_keys = _body_keys_from_hash_or_schema(endpoint)
            overlap = field_names & body_keys if field_names and body_keys else set()
            confidence = 0.75 if overlap else 0.65
            method = "form_body_field_match" if overlap else "heuristic"
            mappings.append(
                {
                    "api_endpoint_id": str(endpoint.get("endpoint_id") or ""),
                    "page_id": page_id,
                    "form_id": str(form.get("form_id") or ""),
                    "element_id": None,
                    "flow_id": None,
                    "trigger_action": {"action": "submit", "form_id": form.get("form_id")},
                    "confidence": _clamp_confidence(confidence),
                    "correlation_method": method,
                    "review_required": confidence < REVIEW_THRESHOLD,
                }
            )
    return mappings


def correlate_openapi_heuristic(
    *,
    pages: list[dict[str, Any]],
    api_endpoints: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Low-confidence mappings for OpenAPI-only endpoints."""
    mappings: list[dict[str, Any]] = []
    for endpoint in api_endpoints:
        if str(endpoint.get("source") or "") not in {"openapi", "both"}:
            continue
        pattern = str(endpoint.get("path_pattern") or endpoint.get("path") or "").lower()
        segments = [segment for segment in pattern.split("/") if segment and segment != "{id}"]
        if not segments:
            continue
        keyword = segments[-1]
        for page in pages:
            page_id = str(page.get("page_id") or "")
            blob = f"{page.get('title') or ''} {page.get('url') or ''}".lower()
            if keyword not in blob:
                continue
            mappings.append(
                {
                    "api_endpoint_id": str(endpoint.get("endpoint_id") or ""),
                    "page_id": page_id,
                    "form_id": None,
                    "element_id": None,
                    "flow_id": None,
                    "trigger_action": {},
                    "confidence": 0.5 if str(endpoint.get("source")) == "openapi" else 0.55,
                    "correlation_method": "openapi_only",
                    "review_required": True,
                }
            )
    return mappings


def _mapping_key(mapping: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(mapping.get("page_id") or ""),
        str(mapping.get("api_endpoint_id") or ""),
        str(mapping.get("form_id") or ""),
        str(mapping.get("element_id") or ""),
    )


def merge_api_ui_mappings(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge mapping candidates, keeping highest confidence per key."""
    merged: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for group in groups:
        for mapping in group:
            if not mapping.get("api_endpoint_id") or not mapping.get("page_id"):
                continue
            key = _mapping_key(mapping)
            existing = merged.get(key)
            if existing is None or float(mapping.get("confidence") or 0) > float(existing.get("confidence") or 0):
                merged[key] = dict(mapping)
    return list(merged.values())


def build_api_ui_mappings(
    *,
    pages: list[dict[str, Any]],
    forms: list[dict[str, Any]],
    elements: list[dict[str, Any]],
    api_endpoints: list[dict[str, Any]],
    interaction_events_by_page: dict[str, list[dict[str, Any]]] | None = None,
    network_events_by_page: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Build API↔UI mappings from crawl observations and persisted AppMap rows."""
    endpoint_by_pattern = {
        f"{str(endpoint.get('method') or 'GET').upper()} {endpoint.get('path_pattern')}": endpoint
        for endpoint in api_endpoints
    }
    interaction_events_by_page = interaction_events_by_page or {}
    network_events_by_page = network_events_by_page or {}

    groups: list[list[dict[str, Any]]] = []
    for page in pages:
        page_id = str(page.get("page_id") or "")
        page_forms = [form for form in forms if str(form.get("page_id") or "") == page_id]
        page_elements = [element for element in elements if str(element.get("page_id") or "") == page_id]
        groups.append(
            correlate_form_endpoints(
                page_id=page_id,
                forms=page_forms,
                api_endpoints=api_endpoints,
                elements=page_elements,
            )
        )
        groups.append(
            correlate_cic_interactions(
                page_id=page_id,
                interaction_events=interaction_events_by_page.get(page_id, []),
                network_events=network_events_by_page.get(page_id, []),
                forms=page_forms,
                elements=page_elements,
                endpoint_by_pattern=endpoint_by_pattern,
            )
        )

    groups.append(correlate_openapi_heuristic(pages=pages, api_endpoints=api_endpoints))
    return merge_api_ui_mappings(*groups)


def extract_body_keys(post_data: str | bytes | None) -> list[str]:
    if not post_data:
        return []
    try:
        if isinstance(post_data, bytes):
            text = post_data.decode("utf-8", errors="ignore")
        else:
            text = post_data
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(payload, dict):
        return [str(key) for key in payload.keys()]
    return []
