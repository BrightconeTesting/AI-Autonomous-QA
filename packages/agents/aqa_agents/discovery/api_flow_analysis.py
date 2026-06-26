"""QA-oriented API flow analysis derived from the dependency graph."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def _primary_causal_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    causal_types = {"sequential", "ui_chain", "schema_ref"}
    return [
        edge
        for edge in edges
        if edge.get("is_primary", True) and edge.get("edge_type") in causal_types
    ]


def _longest_risk_weighted_path(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> list[str]:
    node_ids = {str(node.get("endpoint_id") or "") for node in nodes}
    risk_by_id = {
        str(node.get("endpoint_id") or ""): int(node.get("risk_score") or 0) for node in nodes
    }
    adjacency: dict[str, list[str]] = defaultdict(list)
    indegree: dict[str, int] = {node_id: 0 for node_id in node_ids}
    for edge in edges:
        from_id = str(edge.get("from_endpoint_id") or "")
        to_id = str(edge.get("to_endpoint_id") or "")
        if from_id in node_ids and to_id in node_ids:
            adjacency[from_id].append(to_id)
            indegree[to_id] += 1

    best_score: dict[str, int] = {node_id: risk_by_id.get(node_id, 0) for node_id in node_ids}
    predecessor: dict[str, str | None] = {node_id: None for node_id in node_ids}
    queue = [node_id for node_id, degree in indegree.items() if degree == 0]
    ordered: list[str] = []
    while queue:
        current = queue.pop(0)
        ordered.append(current)
        for child in adjacency.get(current, []):
            candidate = best_score.get(current, 0) + risk_by_id.get(child, 0)
            if candidate >= best_score.get(child, 0):
                best_score[child] = candidate
                predecessor[child] = current
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)

    if not ordered:
        return []
    end_node = max(node_ids, key=lambda node_id: best_score.get(node_id, 0))
    path: list[str] = []
    current: str | None = end_node
    while current:
        path.append(current)
        current = predecessor.get(current)
    path.reverse()
    return path


def build_api_flow_analysis(
    graph: dict[str, Any],
    api_endpoints: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Classify entry/leaf nodes, depth distribution, and critical risk path."""
    _ = api_endpoints
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    if not nodes:
        return {
            "entry_endpoint_ids": [],
            "leaf_endpoint_ids": [],
            "critical_path_endpoint_ids": [],
            "max_depth": 0,
            "depth_counts": {},
            "parallel_group_count": 0,
        }

    entry_endpoint_ids = [
        str(node.get("endpoint_id") or "")
        for node in nodes
        if node.get("is_entry")
    ]
    leaf_endpoint_ids = [
        str(node.get("endpoint_id") or "")
        for node in nodes
        if node.get("is_leaf")
    ]
    depth_counts: dict[int, int] = defaultdict(int)
    for node in nodes:
        depth_counts[int(node.get("depth") or 0)] += 1

    parallel_groups = {
        str(edge.get("parallel_group_id"))
        for edge in edges
        if edge.get("parallel_group_id")
    }
    causal_edges = _primary_causal_edges(edges)
    critical_path = _longest_risk_weighted_path(nodes, causal_edges)

    return {
        "entry_endpoint_ids": entry_endpoint_ids,
        "leaf_endpoint_ids": leaf_endpoint_ids,
        "critical_path_endpoint_ids": critical_path,
        "max_depth": max((int(node.get("depth") or 0) for node in nodes), default=0),
        "depth_counts": {str(depth): count for depth, count in sorted(depth_counts.items())},
        "parallel_group_count": len(parallel_groups),
    }
