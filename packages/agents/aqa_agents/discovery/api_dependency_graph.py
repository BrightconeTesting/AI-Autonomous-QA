"""API dependency graph builder (DISCOVERY-AGENT-VISION-SPEC §9.7)."""

from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from typing import Any

SEQUENTIAL_WINDOW_MS = 5000.0
PARALLEL_WINDOW_MS = 50.0
FORK_WINDOW_MS = 500.0
_AUTH_PATH_KEYWORDS = ("login", "auth", "token", "session", "oauth", "signin", "sign-in")
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_CAUSAL_EDGE_TYPES = frozenset({"sequential", "ui_chain", "schema_ref"})


def _endpoint_key(method: str, path_pattern: str) -> str:
    return f"{str(method or 'GET').upper()} {path_pattern}"


def _clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, round(value, 3)))


def risk_tier_from_score(score: int | None) -> str | None:
    if score is None:
        return None
    if score <= 25:
        return "low"
    if score <= 50:
        return "medium"
    if score <= 75:
        return "high"
    return "critical"


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


def _collect_schema_field_names(value: Any, names: set[str] | None = None) -> set[str]:
    names = names or set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key not in ("$ref", "type", "format", "description", "required"):
                names.add(str(key))
            _collect_schema_field_names(item, names)
    elif isinstance(value, list):
        for item in value:
            _collect_schema_field_names(item, names)
    return names


def _is_auth_endpoint(endpoint: dict[str, Any]) -> bool:
    blob = f"{endpoint.get('path_pattern') or ''} {endpoint.get('path') or ''}".lower()
    return any(keyword in blob for keyword in _AUTH_PATH_KEYWORDS)


def _is_session_check_endpoint(endpoint: dict[str, Any]) -> bool:
    """GET endpoints that validate an existing session — not login."""
    method = str(endpoint.get("method") or "GET").upper()
    if method != "GET":
        return False
    blob = f"{endpoint.get('path_pattern') or ''} {endpoint.get('path') or ''}".lower()
    return any(
        token in blob
        for token in ("/me", "/whoami", "/current-user", "/current_user", "/session/verify", "/validate")
    )


def _is_login_endpoint(endpoint: dict[str, Any]) -> bool:
    if _is_session_check_endpoint(endpoint):
        return False
    if not _is_auth_endpoint(endpoint):
        return False
    method = str(endpoint.get("method") or "GET").upper()
    return method in _MUTATING_METHODS


def _path_param_tokens(path_pattern: str) -> list[str]:
    return [token.lower() for token in re.findall(r"\{([^}]+)\}", path_pattern or "")]


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
    delta_ms: float | None = None,
) -> None:
    if not from_endpoint_id or not to_endpoint_id or from_endpoint_id == to_endpoint_id:
        return
    key = _edge_key(from_endpoint_id, to_endpoint_id, edge_type)
    existing = merged.get(key)
    if existing is None:
        edge: dict[str, Any] = {
            "from_endpoint_id": from_endpoint_id,
            "to_endpoint_id": to_endpoint_id,
            "edge_type": edge_type,
            "confidence": _clamp_confidence(confidence),
            "observed_count": 1,
            "dependency_keys": [],
            "parallel_group_id": None,
            "is_primary": True,
        }
        if delta_ms is not None:
            edge["delta_ms"] = delta_ms
        merged[key] = edge
        return
    existing["observed_count"] = int(existing.get("observed_count") or 0) + 1
    existing["confidence"] = _clamp_confidence(
        max(float(existing.get("confidence") or 0), confidence)
    )
    if delta_ms is not None:
        existing["delta_ms"] = min(float(existing.get("delta_ms") or delta_ms), delta_ms)


def infer_sequential_edges(
    *,
    api_endpoints: list[dict[str, Any]],
    network_events_by_page: dict[str, list[dict[str, Any]]],
    key_to_id: dict[str, str],
    window_ms: float = SEQUENTIAL_WINDOW_MS,
) -> list[dict[str, Any]]:
    """Infer sequential edges: fork bursts fan from parent; otherwise nearest successor."""
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    for events in network_events_by_page.values():
        ordered = sorted(events, key=lambda item: float(item.get("timestamp_ms") or 0))
        index = 0
        while index < len(ordered):
            first = ordered[index]
            first_key = _endpoint_key(str(first.get("method") or "GET"), str(first.get("path_pattern") or ""))
            from_id = key_to_id.get(first_key)
            first_ts = float(first.get("timestamp_ms") or 0)
            if from_id is None:
                index += 1
                continue

            burst_end = index + 1
            while burst_end < len(ordered):
                delta = float(ordered[burst_end].get("timestamp_ms") or 0) - first_ts
                if delta <= 0 or delta > FORK_WINDOW_MS:
                    break
                burst_end += 1

            if burst_end > index + 2:
                for child_index in range(index + 1, burst_end):
                    second = ordered[child_index]
                    second_key = _endpoint_key(
                        str(second.get("method") or "GET"), str(second.get("path_pattern") or "")
                    )
                    to_id = key_to_id.get(second_key)
                    if to_id is None or to_id == from_id:
                        continue
                    delta = float(second.get("timestamp_ms") or 0) - first_ts
                    proximity = 1.0 - (delta / window_ms)
                    confidence = 0.7 + 0.3 * max(proximity, 0.0)
                    _add_edge(
                        merged,
                        from_endpoint_id=from_id,
                        to_endpoint_id=to_id,
                        edge_type="sequential",
                        confidence=confidence,
                        delta_ms=delta,
                    )
                index = burst_end
                continue

            if index + 1 < len(ordered):
                second = ordered[index + 1]
                second_ts = float(second.get("timestamp_ms") or 0)
                delta = second_ts - first_ts
                if 0 < delta <= window_ms:
                    second_key = _endpoint_key(
                        str(second.get("method") or "GET"), str(second.get("path_pattern") or "")
                    )
                    to_id = key_to_id.get(second_key)
                    if to_id is not None and to_id != from_id:
                        proximity = 1.0 - (delta / window_ms)
                        confidence = 0.7 + 0.3 * proximity
                        _add_edge(
                            merged,
                            from_endpoint_id=from_id,
                            to_endpoint_id=to_id,
                            edge_type="sequential",
                            confidence=confidence,
                            delta_ms=delta,
                        )
            index += 1
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
    auth_intelligence: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    auth = auth_intelligence or {}
    login_id = str(auth.get("login_api_endpoint_id") or "") or None
    protected = {str(item) for item in (auth.get("protected_api_endpoint_ids") or []) if item}

    login_ids = [login_id] if login_id else []
    if not login_ids:
        login_ids = [
            str(endpoint.get("endpoint_id") or "")
            for endpoint in api_endpoints
            if _is_login_endpoint(endpoint)
        ]
    login_ids = [item for item in login_ids if item]
    if not login_ids:
        return []

    for auth_id in login_ids:
        targets = protected if protected else [
            str(endpoint.get("endpoint_id") or "")
            for endpoint in api_endpoints
            if not _is_auth_endpoint(endpoint)
        ]
        for to_id in targets:
            if not to_id or to_id == auth_id:
                continue
            _add_edge(
                merged,
                from_endpoint_id=auth_id,
                to_endpoint_id=to_id,
                edge_type="auth_dependency",
                confidence=0.65,
            )
    return list(merged.values())


def prune_auth_dependency_edges(
    edges: list[dict[str, Any]],
    *,
    auth_intelligence: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Keep auth edges only from the canonical login endpoint to protected targets."""
    auth = auth_intelligence or {}
    login_id = str(auth.get("login_api_endpoint_id") or "") or None
    protected = {str(item) for item in (auth.get("protected_api_endpoint_ids") or []) if item}
    if not login_id:
        return [edge for edge in edges if edge.get("edge_type") != "auth_dependency"]

    pruned: list[dict[str, Any]] = []
    for edge in edges:
        if edge.get("edge_type") != "auth_dependency":
            pruned.append(edge)
            continue
        from_id = str(edge.get("from_endpoint_id") or "")
        to_id = str(edge.get("to_endpoint_id") or "")
        if from_id != login_id:
            continue
        if protected and to_id not in protected:
            continue
        pruned.append(edge)
    return pruned


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
                item = dict(edge)
                item.setdefault("dependency_keys", [])
                item.setdefault("parallel_group_id", None)
                item.setdefault("is_primary", True)
                merged[key] = item
                continue
            existing["observed_count"] = int(existing.get("observed_count") or 0) + int(
                edge.get("observed_count") or 1
            )
            existing["confidence"] = _clamp_confidence(
                max(float(existing.get("confidence") or 0), float(edge.get("confidence") or 0))
            )
    return list(merged.values())


def prune_sequential_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep fork branches from a parent; otherwise retain the strongest successor."""
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    other: list[dict[str, Any]] = []
    for edge in edges:
        if edge.get("edge_type") == "sequential":
            by_source[str(edge.get("from_endpoint_id") or "")].append(edge)
        else:
            other.append(edge)

    pruned: list[dict[str, Any]] = []
    for _, group in by_source.items():
        fork_candidates = [
            edge
            for edge in group
            if float(edge.get("delta_ms") or 10**9) <= FORK_WINDOW_MS
        ]
        if len(fork_candidates) >= 2:
            for edge in fork_candidates:
                pruned.append(edge)
            for edge in group:
                if edge not in fork_candidates:
                    dropped = dict(edge)
                    dropped["is_primary"] = False
                    pruned.append(dropped)
            continue

        parallel_candidates = [
            edge
            for edge in group
            if float(edge.get("delta_ms") or 10**9) <= PARALLEL_WINDOW_MS
        ]
        if len(parallel_candidates) >= 2:
            for edge in parallel_candidates:
                pruned.append(edge)
            for edge in group:
                if edge not in parallel_candidates:
                    dropped = dict(edge)
                    dropped["is_primary"] = False
                    pruned.append(dropped)
            continue

        if not group:
            continue
        best = max(group, key=lambda item: float(item.get("confidence") or 0))
        pruned.append(best)
        for edge in group:
            if edge is not best:
                dropped = dict(edge)
                dropped["is_primary"] = False
                pruned.append(dropped)
    return other + pruned


def break_cycles(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove lowest-confidence primary causal edge per detected back-edge."""
    causal = [
        edge
        for edge in edges
        if edge.get("is_primary", True) and edge.get("edge_type") in _CAUSAL_EDGE_TYPES
    ]
    if not causal:
        return edges

    adjacency: dict[str, list[dict[str, Any]]] = defaultdict(list)
    nodes: set[str] = set()
    for edge in causal:
        from_id = str(edge.get("from_endpoint_id") or "")
        to_id = str(edge.get("to_endpoint_id") or "")
        if from_id and to_id:
            adjacency[from_id].append(edge)
            nodes.add(from_id)
            nodes.add(to_id)

    removed: set[tuple[str, str, str]] = set()

    def _find_back_edge() -> dict[str, Any] | None:
        state: dict[str, int] = {}  # 0=unvisited, 1=active, 2=done

        def dfs(node: str) -> dict[str, Any] | None:
            state[node] = 1
            for edge in adjacency.get(node, []):
                to_id = str(edge.get("to_endpoint_id") or "")
                if not to_id:
                    continue
                child_state = state.get(to_id, 0)
                if child_state == 1:
                    return edge
                if child_state == 0:
                    found = dfs(to_id)
                    if found is not None:
                        return found
            state[node] = 2
            return None

        for node in nodes:
            if state.get(node, 0) == 0:
                found = dfs(node)
                if found is not None:
                    return found
        return None

    for _ in range(len(causal)):
        back_edge = _find_back_edge()
        if back_edge is None:
            break
        key = _edge_key(
            str(back_edge.get("from_endpoint_id") or ""),
            str(back_edge.get("to_endpoint_id") or ""),
            str(back_edge.get("edge_type") or ""),
        )
        removed.add(key)
        from_id = str(back_edge.get("from_endpoint_id") or "")
        adjacency[from_id] = [
            edge
            for edge in adjacency.get(from_id, [])
            if _edge_key(
                str(edge.get("from_endpoint_id") or ""),
                str(edge.get("to_endpoint_id") or ""),
                str(edge.get("edge_type") or ""),
            )
            not in removed
        ]

    output: list[dict[str, Any]] = []
    for edge in edges:
        key = _edge_key(
            str(edge.get("from_endpoint_id") or ""),
            str(edge.get("to_endpoint_id") or ""),
            str(edge.get("edge_type") or ""),
        )
        if key in removed:
            item = dict(edge)
            item["is_primary"] = False
            output.append(item)
        else:
            output.append(edge)
    return output


def detect_parallel_groups(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Tag sibling sequential edges from the same parent (fork or tight parallel burst)."""
    by_parent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        if edge.get("edge_type") != "sequential" or not edge.get("is_primary", True):
            continue
        by_parent[str(edge.get("from_endpoint_id") or "")].append(edge)

    group_index = 0
    for parent_id, group in by_parent.items():
        if len(group) < 2:
            continue
        group_index += 1
        group_id = f"parallel-{parent_id[:8]}-{group_index}"
        for edge in group:
            edge["parallel_group_id"] = group_id
    return edges


def infer_dependency_keys(
    edges: list[dict[str, Any]],
    *,
    api_endpoints: list[dict[str, Any]],
    network_events_by_page: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    endpoint_by_id = {str(item.get("endpoint_id") or ""): item for item in api_endpoints}
    body_keys_by_id: dict[str, set[str]] = defaultdict(set)
    for endpoint in api_endpoints:
        endpoint_id = str(endpoint.get("endpoint_id") or "")
        for key in endpoint.get("body_keys") or []:
            body_keys_by_id[endpoint_id].add(str(key))

    if network_events_by_page:
        for events in network_events_by_page.values():
            for event in events:
                endpoint_id = str(event.get("api_endpoint_id") or "")
                if not endpoint_id:
                    continue
                for key in event.get("body_keys") or []:
                    body_keys_by_id[endpoint_id].add(str(key))

    for edge in edges:
        from_id = str(edge.get("from_endpoint_id") or "")
        to_id = str(edge.get("to_endpoint_id") or "")
        from_ep = endpoint_by_id.get(from_id, {})
        to_ep = endpoint_by_id.get(to_id, {})
        keys: set[str] = set()

        from_fields = _collect_schema_field_names(from_ep.get("response_schema") or {})
        to_fields = _collect_schema_field_names(to_ep.get("request_schema") or {})
        keys |= {field for field in from_fields & to_fields if field not in ("properties", "items")}

        for token in _path_param_tokens(str(to_ep.get("path_pattern") or "")):
            if token in from_fields or token.endswith("id"):
                keys.add(token)

        for key in body_keys_by_id.get(to_id, set()):
            if key in from_fields or key.endswith("Id") or key.endswith("_id"):
                keys.add(key)

        edge["dependency_keys"] = sorted(keys)[:8]
    return edges


def _page_module_map(modules: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for module in modules:
        for page_id in module.get("pages") or []:
            mapping[str(page_id)] = module
    return mapping


def assign_module_ids(
    nodes: list[dict[str, Any]],
    *,
    api_endpoints: list[dict[str, Any]],
    modules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    page_to_module = _page_module_map(modules)
    endpoint_by_id = {str(item.get("endpoint_id") or ""): item for item in api_endpoints}
    for node in nodes:
        endpoint = endpoint_by_id.get(str(node.get("endpoint_id") or ""), {})
        module_id: str | None = None
        module_name: str | None = None
        for page_id in endpoint.get("seen_on_page_ids") or []:
            module = page_to_module.get(str(page_id))
            if module:
                module_id = str(module.get("module_id") or "")
                module_name = str(module.get("name") or module_id)
                break
        if module_id is None:
            path = str(endpoint.get("path_pattern") or endpoint.get("path") or "")
            segments = [segment for segment in path.strip("/").split("/") if segment and not segment.startswith("{")]
            if segments:
                module_name = segments[-1].replace("-", " ").replace("_", " ").title()
        node["module_id"] = module_id
        node["module_name"] = module_name
    return nodes


def enrich_auth_metadata(
    nodes: list[dict[str, Any]],
    *,
    auth_intelligence: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    auth = auth_intelligence or {}
    login_id = str(auth.get("login_api_endpoint_id") or "") or None
    protected = {str(item) for item in (auth.get("protected_api_endpoint_ids") or [])}
    node_by_id = {str(node.get("endpoint_id") or ""): node for node in nodes}
    for node in nodes:
        endpoint_id = str(node.get("endpoint_id") or "")
        requires_auth = endpoint_id in protected
        inherited_from: str | None = login_id if requires_auth and login_id else None
        is_login = endpoint_id == login_id if login_id else _is_login_endpoint(node)
        is_session_check = _is_session_check_endpoint(node)
        if _is_auth_endpoint(node):
            requires_auth = False
            inherited_from = None
        node["requires_auth"] = requires_auth
        node["auth_inherited_from"] = inherited_from
        node["is_login_endpoint"] = is_login
        node["is_session_check"] = is_session_check and not is_login
        if requires_auth and inherited_from and inherited_from in node_by_id:
            login_node = node_by_id[inherited_from]
            node["auth_source_label"] = f"{login_node.get('method', 'POST')} {login_node.get('path_pattern', '')}"
    return nodes


def compute_node_depths(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    node_ids = {str(node.get("endpoint_id") or "") for node in nodes}
    primary_edges = [
        edge
        for edge in edges
        if edge.get("is_primary", True) and edge.get("edge_type") in _CAUSAL_EDGE_TYPES
    ]
    indegree: dict[str, int] = {node_id: 0 for node_id in node_ids}
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in primary_edges:
        from_id = str(edge.get("from_endpoint_id") or "")
        to_id = str(edge.get("to_endpoint_id") or "")
        if from_id in node_ids and to_id in node_ids:
            adjacency[from_id].append(to_id)
            indegree[to_id] = indegree.get(to_id, 0) + 1

    queue = deque([node_id for node_id, degree in indegree.items() if degree == 0])
    depths: dict[str, int] = {node_id: 0 for node_id in node_ids}
    while queue:
        current = queue.popleft()
        for child in adjacency.get(current, []):
            depths[child] = max(depths.get(child, 0), depths.get(current, 0) + 1)
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)

    for node_id in node_ids:
        if node_id not in depths or indegree.get(node_id, 0) > 0:
            depths[node_id] = depths.get(node_id, 0)

    max_depth = max(depths.values()) if depths else 0
    for node in nodes:
        endpoint_id = str(node.get("endpoint_id") or "")
        node["depth"] = int(depths.get(endpoint_id, 0))
    return nodes, max_depth


def classify_entry_leaf(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    node_ids = {str(node.get("endpoint_id") or "") for node in nodes}
    primary_edges = [
        edge
        for edge in edges
        if edge.get("is_primary", True) and edge.get("edge_type") in _CAUSAL_EDGE_TYPES
    ]
    out_degree: dict[str, int] = defaultdict(int)
    in_degree: dict[str, int] = defaultdict(int)
    for edge in primary_edges:
        from_id = str(edge.get("from_endpoint_id") or "")
        to_id = str(edge.get("to_endpoint_id") or "")
        if from_id in node_ids and to_id in node_ids:
            out_degree[from_id] += 1
            in_degree[to_id] += 1

    for node in nodes:
        endpoint_id = str(node.get("endpoint_id") or "")
        node["is_entry"] = in_degree.get(endpoint_id, 0) == 0
        node["is_leaf"] = out_degree.get(endpoint_id, 0) == 0
        node["branching_factor"] = out_degree.get(endpoint_id, 0)
    return nodes


def _merge_body_keys_from_timeline(
    api_endpoints: list[dict[str, Any]],
    network_events_by_page: dict[str, list[dict[str, Any]]],
    key_to_id: dict[str, str],
) -> list[dict[str, Any]]:
    keys_by_endpoint: dict[str, set[str]] = defaultdict(set)
    for events in network_events_by_page.values():
        for event in events:
            key = _endpoint_key(str(event.get("method") or "GET"), str(event.get("path_pattern") or ""))
            endpoint_id = key_to_id.get(key)
            if not endpoint_id:
                continue
            for body_key in event.get("body_keys") or []:
                keys_by_endpoint[endpoint_id].add(str(body_key))

    enriched: list[dict[str, Any]] = []
    for endpoint in api_endpoints:
        item = dict(endpoint)
        endpoint_id = str(endpoint.get("endpoint_id") or "")
        existing = {str(key) for key in (endpoint.get("body_keys") or [])}
        item["body_keys"] = sorted(existing | keys_by_endpoint.get(endpoint_id, set()))
        enriched.append(item)
    return enriched


def enrich_api_dependency_graph(
    graph: dict[str, Any],
    *,
    api_endpoints: list[dict[str, Any]],
    modules: list[dict[str, Any]] | None = None,
    auth_intelligence: dict[str, Any] | None = None,
    network_events_by_page: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Attach scoring, module, auth, and topology metadata to graph nodes."""
    nodes = [dict(node) for node in (graph.get("nodes") or [])]
    edges = [dict(edge) for edge in (graph.get("edges") or [])]
    endpoint_by_id = {str(item.get("endpoint_id") or ""): item for item in api_endpoints}

    for node in nodes:
        endpoint_id = str(node.get("endpoint_id") or "")
        endpoint = endpoint_by_id.get(endpoint_id, {})
        risk_score = endpoint.get("risk_score")
        node["seen_count"] = int(endpoint.get("seen_count") or 1)
        node["risk_score"] = risk_score
        node["risk_tier"] = risk_tier_from_score(int(risk_score) if risk_score is not None else None)
        node.setdefault("requires_auth", False)
        node.setdefault("auth_inherited_from", None)
        node.setdefault("module_id", None)
        node.setdefault("module_name", None)
        node.setdefault("depth", 0)
        node.setdefault("is_entry", False)
        node.setdefault("is_leaf", False)
        node.setdefault("branching_factor", 0)
        node.setdefault("is_login_endpoint", False)
        node.setdefault("is_session_check", False)

    edges = infer_dependency_keys(
        edges,
        api_endpoints=api_endpoints,
        network_events_by_page=network_events_by_page,
    )
    if auth_intelligence:
        edges = prune_auth_dependency_edges(edges, auth_intelligence=auth_intelligence)
    nodes = assign_module_ids(nodes, api_endpoints=api_endpoints, modules=modules or [])
    nodes = enrich_auth_metadata(nodes, auth_intelligence=auth_intelligence)
    nodes, _ = compute_node_depths(nodes, edges)
    nodes = classify_entry_leaf(nodes, edges)

    return {"nodes": nodes, "edges": edges}


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
    api_endpoints = _merge_body_keys_from_timeline(api_endpoints, network_events_by_page, key_to_id)
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
    edges = prune_sequential_edges(edges)
    edges = break_cycles(edges)
    edges = detect_parallel_groups(edges)

    return {"nodes": nodes, "edges": edges}
