"""API dependency graph builder (DISCOVERY-AGENT-VISION-SPEC §9.7)."""

from __future__ import annotations

import json
from typing import Any

SEQUENTIAL_WINDOW_MS = 5000.0
_AUTH_PATH_KEYWORDS = ("login", "auth", "token", "session", "oauth", "signin", "sign-in")
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _endpoint_key(method: str, path_pattern: str) -> str:
    return f"{str(method or 'GET').upper()} {path_pattern}"


def _clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, round(value, 3)))


def _collect_schema_refs(value: Any, refs: set[str] | None = None) -> set[str]:
    refs = refs or set()
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str) and ref:
            refs.add(ref.rsplit("/", 1)[-1].lower())
        for item in value.values():
            _collect_schema_refs(item, refs)
    elif isinstance(value, list):
        for item in value:
            _collect_schema_refs(item, refs)
    return refs


def _is_auth_endpoint(endpoint: dict[str, Any]) -> bool:
    blob = f"{endpoint.get('path_pattern') or ''} {endpoint.get('path') or ''}".lower()
    return any(keyword in blob for keyword in _AUTH_PATH_KEYWORDS)


def _build_nodes(api_endpoints: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    nodes: list[dict[str, Any]] = []
    key_to_id: dict[str, str] = {}
    for endpoint in api_endpoints:
        endpoint_id = str(endpoint.get("endpoint_id") or "")
        if not endpoint_id:
            continue
        method = str(endpoint.get("method") or "GET").upper()
        path_pattern = str(endpoint.get("path_pattern") or endpoint.get("path") or "")
        key = _endpoint_key(method, path_pattern)
        key_to_id[key] = endpoint_id
        nodes.append(
            {
                "endpoint_id": endpoint_id,
                "method": method,
                "path": str(endpoint.get("path") or path_pattern),
                "path_pattern": path_pattern,
            }
        )
    return nodes, key_to_id


def _edge_key(from_id: str, to_id: str, edge_type: str) -> tuple[str, str, str]:
    return (from_id, to_id, edge_type)


def _add_edge(
    merged: dict[tuple[str, str, str], dict[str, Any]],
    *,
    from_endpoint_id: str,
    to_endpoint_id: str,
    edge_type: str,
    confidence: float,
) -> None:
    if not from_endpoint_id or not to_endpoint_id or from_endpoint_id == to_endpoint_id:
        return
    key = _edge_key(from_endpoint_id, to_endpoint_id, edge_type)
    existing = merged.get(key)
    if existing is None:
        merged[key] = {
            "from_endpoint_id": from_endpoint_id,
            "to_endpoint_id": to_endpoint_id,
            "edge_type": edge_type,
            "confidence": _clamp_confidence(confidence),
            "observed_count": 1,
        }
        return
    existing["observed_count"] = int(existing.get("observed_count") or 0) + 1
    existing["confidence"] = _clamp_confidence(
        max(float(existing.get("confidence") or 0), confidence)
    )


def infer_sequential_edges(
    *,
    api_endpoints: list[dict[str, Any]],
    network_events_by_page: dict[str, list[dict[str, Any]]],
    key_to_id: dict[str, str],
    window_ms: float = SEQUENTIAL_WINDOW_MS,
) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    for events in network_events_by_page.values():
        ordered = sorted(events, key=lambda item: float(item.get("timestamp_ms") or 0))
        for index, first in enumerate(ordered):
            first_key = _endpoint_key(str(first.get("method") or "GET"), str(first.get("path_pattern") or ""))
            from_id = key_to_id.get(first_key)
            if from_id is None:
                continue
            first_ts = float(first.get("timestamp_ms") or 0)
            for second in ordered[index + 1 :]:
                second_ts = float(second.get("timestamp_ms") or 0)
                delta = second_ts - first_ts
                if delta <= 0:
                    continue
                if delta > window_ms:
                    break
                second_key = _endpoint_key(
                    str(second.get("method") or "GET"), str(second.get("path_pattern") or "")
                )
                to_id = key_to_id.get(second_key)
                if to_id is None:
                    continue
                proximity = 1.0 - (delta / window_ms)
                confidence = 0.7 + 0.3 * proximity
                _add_edge(
                    merged,
                    from_endpoint_id=from_id,
                    to_endpoint_id=to_id,
                    edge_type="sequential",
                    confidence=confidence,
                )
    return list(merged.values())


def infer_schema_ref_edges(
    *,
    api_endpoints: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    endpoint_refs: list[tuple[str, set[str]]] = []
    for endpoint in api_endpoints:
        endpoint_id = str(endpoint.get("endpoint_id") or "")
        if not endpoint_id:
            continue
        refs = _collect_schema_refs(endpoint.get("request_schema") or {})
        refs |= _collect_schema_refs(endpoint.get("response_schema") or {})
        endpoint_refs.append((endpoint_id, refs))

    for from_id, refs in endpoint_refs:
        if not refs:
            continue
        for to_endpoint in api_endpoints:
            to_id = str(to_endpoint.get("endpoint_id") or "")
            if not to_id or to_id == from_id:
                continue
            blob = f"{to_endpoint.get('path_pattern') or ''} {to_endpoint.get('path') or ''}".lower()
            schema_blob = json.dumps(
                {
                    "request": to_endpoint.get("request_schema") or {},
                    "response": to_endpoint.get("response_schema") or {},
                }
            ).lower()
            for ref in refs:
                if ref in blob or ref in schema_blob:
                    _add_edge(
                        merged,
                        from_endpoint_id=from_id,
                        to_endpoint_id=to_id,
                        edge_type="schema_ref",
                        confidence=0.75,
                    )
    return list(merged.values())


def infer_ui_chain_edges(
    *,
    api_endpoints: list[dict[str, Any]],
    api_ui_mappings: list[dict[str, Any]],
    network_events_by_page: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    endpoint_by_id = {str(item.get("endpoint_id") or ""): item for item in api_endpoints}
    groups: dict[str, list[dict[str, Any]]] = {}
    for mapping in api_ui_mappings:
        page_id = str(mapping.get("page_id") or "")
        form_id = str(mapping.get("form_id") or "")
        element_id = str(mapping.get("element_id") or "")
        trigger = json.dumps(mapping.get("trigger_action") or {}, sort_keys=True)
        group_key = f"{page_id}|{form_id}|{element_id}|{trigger}"
        groups.setdefault(group_key, []).append(mapping)

    for group_key, mappings in groups.items():
        endpoint_ids = [str(item.get("api_endpoint_id") or "") for item in mappings if item.get("api_endpoint_id")]
        unique_ids = list(dict.fromkeys(endpoint_ids))
        if len(unique_ids) < 2:
            continue

        page_id = group_key.split("|", 1)[0]
        events = sorted(
            network_events_by_page.get(page_id, []),
            key=lambda item: float(item.get("timestamp_ms") or 0),
        )

        def _event_timestamp(endpoint_id: str) -> float:
            endpoint = endpoint_by_id.get(endpoint_id, {})
            method = str(endpoint.get("method") or "GET").upper()
            pattern = str(endpoint.get("path_pattern") or "")
            for event in events:
                if (
                    str(event.get("method") or "GET").upper() == method
                    and str(event.get("path_pattern") or "") == pattern
                ):
                    return float(event.get("timestamp_ms") or 0)
            return 10**9

        ordered_ids = sorted(unique_ids, key=_event_timestamp)
        for index in range(len(ordered_ids) - 1):
            _add_edge(
                merged,
                from_endpoint_id=ordered_ids[index],
                to_endpoint_id=ordered_ids[index + 1],
                edge_type="ui_chain",
                confidence=0.8,
            )
    return list(merged.values())


def infer_auth_dependency_edges(
    *,
    api_endpoints: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    auth_ids = [str(endpoint.get("endpoint_id") or "") for endpoint in api_endpoints if _is_auth_endpoint(endpoint)]
    auth_ids = [item for item in auth_ids if item]
    if not auth_ids:
        return []
    for auth_id in auth_ids:
        for endpoint in api_endpoints:
            to_id = str(endpoint.get("endpoint_id") or "")
            if not to_id or to_id == auth_id or _is_auth_endpoint(endpoint):
                continue
            method = str(endpoint.get("method") or "GET").upper()
            if method in _MUTATING_METHODS or method == "GET":
                _add_edge(
                    merged,
                    from_endpoint_id=auth_id,
                    to_endpoint_id=to_id,
                    edge_type="auth_dependency",
                    confidence=0.65,
                )
    return list(merged.values())


def merge_dependency_edges(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    for group in groups:
        for edge in group:
            key = _edge_key(
                str(edge.get("from_endpoint_id") or ""),
                str(edge.get("to_endpoint_id") or ""),
                str(edge.get("edge_type") or ""),
            )
            if not key[0] or not key[1] or not key[2]:
                continue
            existing = merged.get(key)
            if existing is None:
                merged[key] = dict(edge)
                continue
            existing["observed_count"] = int(existing.get("observed_count") or 0) + int(
                edge.get("observed_count") or 1
            )
            existing["confidence"] = _clamp_confidence(
                max(float(existing.get("confidence") or 0), float(edge.get("confidence") or 0))
            )
    return list(merged.values())


def build_api_dependency_graph(
    *,
    api_endpoints: list[dict[str, Any]],
    api_ui_mappings: list[dict[str, Any]] | None = None,
    network_events_by_page: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Build directed API dependency graph nodes and edges."""
    api_ui_mappings = api_ui_mappings or []
    network_events_by_page = network_events_by_page or {}
    if len(api_endpoints) < 2:
        return {"nodes": [], "edges": []}

    nodes, key_to_id = _build_nodes(api_endpoints)
    if len(nodes) < 2:
        return {"nodes": nodes, "edges": []}

    enriched_events_by_page: dict[str, list[dict[str, Any]]] = {}
    for page_id, events in network_events_by_page.items():
        enriched_events: list[dict[str, Any]] = []
        for event in events:
            item = dict(event)
            key = _endpoint_key(str(item.get("method") or "GET"), str(item.get("path_pattern") or ""))
            item["api_endpoint_id"] = key_to_id.get(key)
            enriched_events.append(item)
        enriched_events_by_page[page_id] = enriched_events

    edges = merge_dependency_edges(
        infer_sequential_edges(
            api_endpoints=api_endpoints,
            network_events_by_page=enriched_events_by_page,
            key_to_id=key_to_id,
        ),
        infer_schema_ref_edges(api_endpoints=api_endpoints),
        infer_ui_chain_edges(
            api_endpoints=api_endpoints,
            api_ui_mappings=api_ui_mappings,
            network_events_by_page=enriched_events_by_page,
        ),
        infer_auth_dependency_edges(api_endpoints=api_endpoints),
    )
    return {"nodes": nodes, "edges": edges}
