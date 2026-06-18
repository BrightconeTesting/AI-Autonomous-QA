"""Rule-based flow structuring from crawled pages (Day 20, SPEC §17.1)."""

from __future__ import annotations

from collections import defaultdict
from urllib.parse import urlparse, urlunparse


def _normalize_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https", "file") or not parsed.netloc:
        return (url or "").strip()
    host = parsed.hostname.lower() if parsed.hostname else ""
    port = parsed.port
    default_port = 443 if parsed.scheme == "https" else 80
    netloc = host if port in (None, default_port) else f"{host}:{port}"
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    fragment = parsed.fragment
    if fragment and (fragment.startswith("/") or fragment.startswith("!")):
        return urlunparse((parsed.scheme.lower(), netloc, path, "", "", fragment))
    if parsed.query:
        return urlunparse((parsed.scheme.lower(), netloc, path, "", parsed.query, ""))
    return urlunparse((parsed.scheme.lower(), netloc, path, "", "", ""))


def _module_key(url: str) -> str:
    path = urlparse(url).path
    parts = [part for part in path.split("/") if part]
    if "index.php" in parts:
        index = parts.index("index.php")
        if index + 1 < len(parts):
            return parts[index + 1].lower()
    if len(parts) >= 2:
        return parts[-2].lower()
    if parts:
        return parts[-1].lower()
    fragment = urlparse(url).fragment
    if fragment:
        return fragment.strip("/").split("/")[0].lower() or "root"
    return "root"


def _flow_name(module: str) -> str:
    label = module.replace("-", " ").replace("_", " ").strip() or "root"
    return f"{label.title()} flow"


def _interaction_step(action: dict, to_state: dict) -> dict:
    action_type = action.get("action_type") or "click"
    return {
        "action": action_type,
        "state_key": to_state.get("state_key"),
        "semantic_selector": action.get("semantic_selector"),
        "text_content": action.get("text_content"),
        "role": action.get("role"),
        "value": action.get("value"),
    }


def build_flows_from_pages(pages: list[dict]) -> list[dict]:
    """Group pages by URL module segment and emit flow dicts for persistence."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for page in pages:
        url = page.get("url") or ""
        grouped[_module_key(url)].append(page)

    flows: list[dict] = []
    for module in sorted(grouped.keys()):
        module_pages = sorted(grouped[module], key=lambda item: item.get("url") or "")
        steps = [
            {
                "action": "navigate",
                "page_id": page.get("page_id"),
                "url": page.get("url"),
                "title": page.get("title"),
            }
            for page in module_pages
        ]
        flows.append(
            {
                "name": _flow_name(module),
                "description": f"Rule-based flow for /{module}/ pages ({len(steps)} steps)",
                "steps": steps,
                "source": "crawler",
                "module": module,
            }
        )
    return flows


def _build_discovery_flows(pages: list[dict], discoveries: list[dict]) -> list[dict]:
    """Build navigate → interact → navigate flows for interaction-discovered URLs."""
    page_by_id = {str(page.get("page_id")): page for page in pages}
    page_by_url = {_normalize_url(page.get("url") or ""): page for page in pages}
    flows: list[dict] = []

    for discovery in discoveries:
        if discovery.get("discovered_via") != "interaction":
            continue

        source_page_id = discovery.get("source_page_id")
        source_page = page_by_id.get(str(source_page_id)) if source_page_id else None
        if source_page is None:
            continue

        target_url = discovery.get("url") or ""
        target_page = page_by_url.get(_normalize_url(target_url))
        trigger = discovery.get("trigger_action") or {}
        interact_type = trigger.get("action_type") or "click"

        steps: list[dict] = [
            {
                "action": "navigate",
                "page_id": source_page.get("page_id"),
                "url": source_page.get("url"),
                "title": source_page.get("title"),
            },
            {
                "action": interact_type,
                "state_key": discovery.get("source_state_key"),
                "semantic_selector": trigger.get("semantic_selector"),
                "text_content": trigger.get("text_content"),
                "role": trigger.get("role"),
                "value": trigger.get("value"),
            },
            {
                "action": "navigate",
                "page_id": target_page.get("page_id") if target_page else None,
                "url": target_url,
                "title": target_page.get("title") if target_page else None,
                "discovered_via": "interaction",
            },
        ]

        module = _module_key(source_page.get("url") or "")
        flows.append(
            {
                "name": f"{_flow_name(module)} → discovery (CIC)",
                "description": f"Interaction-discovered route from {source_page.get('url')} to {target_url}",
                "steps": steps,
                "source": "crawler",
                "module": module,
            }
        )

    return flows


def _find_baseline_state(page_states: list[dict]) -> dict | None:
    if not page_states:
        return None
    roots = [state for state in page_states if not state.get("parent_state_key")]
    if roots:
        return min(roots, key=lambda item: item.get("interaction_depth", 0))
    return min(page_states, key=lambda item: item.get("interaction_depth", 0))


def _enumerate_transition_paths(
    baseline_state_id: str,
    transitions: list[dict],
    state_by_id: dict,
    *,
    max_depth: int = 6,
    max_paths: int = 5,
) -> list[list[dict]]:
    """BFS paths from baseline through the transition graph (Phase 4)."""
    adjacency: dict[str, list[tuple[dict, str]]] = defaultdict(list)
    for transition in transitions:
        adjacency[transition.get("from_state_id")].append(
            (transition, transition.get("to_state_id"))
        )

    paths: list[list[dict]] = []
    queue: list[tuple[str, list[dict]]] = [(baseline_state_id, [])]
    seen_path_keys: set[str] = set()

    while queue and len(paths) < max_paths:
        state_id, steps = queue.pop(0)
        children = adjacency.get(state_id, [])
        if not children:
            if steps:
                path_key = "|".join(step.get("state_key", "") for step in steps)
                if path_key not in seen_path_keys:
                    seen_path_keys.add(path_key)
                    paths.append(steps)
            continue

        if len(steps) >= max_depth:
            path_key = "|".join(step.get("state_key", "") for step in steps)
            if path_key not in seen_path_keys:
                seen_path_keys.add(path_key)
                paths.append(steps)
            continue

        for transition, to_state_id in children:
            to_state = state_by_id.get(to_state_id)
            if to_state is None:
                continue
            action = transition.get("action") or {}
            next_steps = steps + [_interaction_step(action, to_state)]
            queue.append((to_state_id, next_steps))

    return paths


def _build_graph_flows_for_page(
    page: dict,
    page_states: list[dict],
    page_transitions: list[dict],
    state_by_id: dict,
    *,
    max_paths: int = 5,
) -> list[dict]:
    """Build one flow per root-to-branch path from the transition graph."""
    baseline = _find_baseline_state(page_states)
    if baseline is None or not page_transitions:
        return []

    navigate_step = {
        "action": "navigate",
        "page_id": page.get("page_id"),
        "url": page.get("url"),
        "title": page.get("title"),
    }

    paths = _enumerate_transition_paths(
        baseline.get("state_id"),
        page_transitions,
        state_by_id,
        max_paths=max_paths,
    )

    module = _module_key(page.get("url") or "")
    flows: list[dict] = []
    for index, path_steps in enumerate(paths, start=1):
        if not path_steps:
            continue
        flows.append(
            {
                "name": f"{_flow_name(module)} path {index} (CIC)",
                "description": f"Transition-graph path on {page.get('url')} ({len(path_steps) + 1} steps)",
                "steps": [navigate_step, *path_steps],
                "source": "crawler",
                "module": module,
            }
        )
    return flows


def build_flows_from_states(
    pages: list[dict],
    states: list[dict],
    transitions: list[dict],
    discoveries: list[dict] | None = None,
    *,
    max_graph_paths_per_page: int = 5,
) -> list[dict]:
    """Build interaction flows from CIC transition graph and discoveries."""
    discovery_flows = _build_discovery_flows(pages, discoveries or [])
    if not states:
        return discovery_flows or build_flows_from_pages(pages)

    state_by_id = {s.get("state_id"): s for s in states}
    graph_flows: list[dict] = []

    for page in pages:
        page_id = page.get("page_id")
        page_states = [state for state in states if state.get("page_id") == page_id]
        page_transitions = [
            transition
            for transition in transitions
            if state_by_id.get(transition.get("from_state_id"), {}).get("page_id") == page_id
        ]
        graph_flows.extend(
            _build_graph_flows_for_page(
                page,
                page_states,
                page_transitions,
                state_by_id,
                max_paths=max_graph_paths_per_page,
            )
        )

    combined = discovery_flows + graph_flows
    if not combined:
        return build_flows_from_pages(pages)
    return combined
