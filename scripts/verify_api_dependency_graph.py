#!/usr/bin/env python3
"""Verify G1 — API dependency graph inference."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import delete

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ["ENCRYPTION_KEY"] = os.getenv("ENCRYPTION_KEY") or ("0123456789abcdef" * 4)
os.environ.setdefault("DATABASE_URL", os.getenv("DATABASE_URL", ""))

from aqa_agents.discovery.api_dependency_graph import (  # noqa: E402
    _build_nodes,
    build_api_dependency_graph,
    enrich_api_dependency_graph,
    infer_auth_dependency_edges,
    infer_sequential_edges,
)
from aqa_agents.discovery.api_flow_analysis import build_api_flow_analysis  # noqa: E402
from aqa_agents.discovery.appmap import load_appmap_for_application  # noqa: E402
from aqa_shared.db.models import ApiEndpoint, Application, Page  # noqa: E402
from aqa_shared.db.session import get_session_factory  # noqa: E402


def _verify_graph_rules() -> bool:
    ep1 = str(uuid.uuid4())
    ep2 = str(uuid.uuid4())
    page_id = str(uuid.uuid4())
    endpoints = [
        {
            "endpoint_id": ep1,
            "method": "GET",
            "path": "/api/users",
            "path_pattern": "/api/users",
            "request_schema": {},
            "response_schema": {},
        },
        {
            "endpoint_id": ep2,
            "method": "GET",
            "path": "/api/users/{id}/permissions",
            "path_pattern": "/api/users/{id}/permissions",
            "request_schema": {},
            "response_schema": {},
        },
        {
            "endpoint_id": str(uuid.uuid4()),
            "method": "POST",
            "path": "/api/auth/login",
            "path_pattern": "/api/auth/login",
            "request_schema": {},
            "response_schema": {},
        },
    ]
    _, key_to_id = _build_nodes(endpoints)
    sequential = infer_sequential_edges(
        api_endpoints=endpoints,
        network_events_by_page={
            page_id: [
                {
                    "method": "GET",
                    "path_pattern": "/api/users",
                    "timestamp_ms": 1000.0,
                },
                {
                    "method": "GET",
                    "path_pattern": "/api/users/{id}/permissions",
                    "timestamp_ms": 2200.0,
                },
            ]
        },
        key_to_id=key_to_id,
    )
    if not sequential or sequential[0].get("edge_type") != "sequential":
        print(f"FAIL sequential edges: {sequential}", file=sys.stderr)
        return False
    if float(sequential[0].get("confidence") or 0) < 0.7:
        print(f"FAIL sequential confidence: {sequential[0]}", file=sys.stderr)
        return False

    auth_edges = infer_auth_dependency_edges(api_endpoints=endpoints)
    if not auth_edges:
        print("FAIL auth_dependency edges missing", file=sys.stderr)
        return False

    graph = build_api_dependency_graph(
        api_endpoints=endpoints,
        api_ui_mappings=[],
        network_events_by_page={
            page_id: [
                {"method": "GET", "path_pattern": "/api/users", "timestamp_ms": 1000.0},
                {"method": "GET", "path_pattern": "/api/users/{id}/permissions", "timestamp_ms": 2200.0},
            ]
        },
    )
    if len(graph.get("nodes") or []) < 2:
        print(f"FAIL graph nodes: {graph}", file=sys.stderr)
        return False
    if len(graph.get("edges") or []) < 2:
        print(f"FAIL graph edges: {graph}", file=sys.stderr)
        return False

    print("OK dependency graph rules (sequential, auth_dependency, merge)")
    return True


def _verify_parallel_fork_and_depth() -> bool:
    login_id = str(uuid.uuid4())
    users_id = str(uuid.uuid4())
    roles_id = str(uuid.uuid4())
    settings_id = str(uuid.uuid4())
    page_id = str(uuid.uuid4())
    endpoints = [
        {
            "endpoint_id": login_id,
            "method": "POST",
            "path": "/api/auth/login",
            "path_pattern": "/api/auth/login",
            "request_schema": {},
            "response_schema": {"properties": {"sessionToken": {"type": "string"}}},
            "seen_on_page_ids": [page_id],
            "seen_count": 1,
            "risk_score": 40,
        },
        {
            "endpoint_id": users_id,
            "method": "GET",
            "path": "/api/users",
            "path_pattern": "/api/users",
            "request_schema": {},
            "response_schema": {},
            "seen_on_page_ids": [page_id],
            "seen_count": 2,
            "risk_score": 20,
        },
        {
            "endpoint_id": roles_id,
            "method": "GET",
            "path": "/api/roles",
            "path_pattern": "/api/roles",
            "request_schema": {},
            "response_schema": {},
            "seen_on_page_ids": [page_id],
            "seen_count": 2,
            "risk_score": 25,
        },
        {
            "endpoint_id": settings_id,
            "method": "GET",
            "path": "/api/settings",
            "path_pattern": "/api/settings",
            "request_schema": {},
            "response_schema": {},
            "seen_on_page_ids": [page_id],
            "seen_count": 1,
            "risk_score": 15,
        },
    ]
    timeline = {
        page_id: [
            {"method": "POST", "path_pattern": "/api/auth/login", "timestamp_ms": 1000.0},
            {"method": "GET", "path_pattern": "/api/users", "timestamp_ms": 1100.0, "body_keys": ["userId"]},
            {"method": "GET", "path_pattern": "/api/roles", "timestamp_ms": 1110.0},
            {"method": "GET", "path_pattern": "/api/settings", "timestamp_ms": 1120.0},
        ]
    }
    graph = build_api_dependency_graph(
        api_endpoints=endpoints,
        network_events_by_page=timeline,
    )
    graph = enrich_api_dependency_graph(
        graph,
        api_endpoints=endpoints,
        modules=[{"module_id": "mod-auth", "name": "Authentication", "pages": [page_id]}],
        auth_intelligence={
            "login_api_endpoint_id": login_id,
            "protected_api_endpoint_ids": [users_id, roles_id, settings_id],
        },
        network_events_by_page=timeline,
    )
    analysis = build_api_flow_analysis(graph, endpoints)

    parallel_edges = [
        edge for edge in graph.get("edges") or [] if edge.get("parallel_group_id")
    ]
    if len(parallel_edges) < 2:
        print(f"FAIL parallel_group edges: {graph.get('edges')}", file=sys.stderr)
        return False

    login_node = next(node for node in graph["nodes"] if node["endpoint_id"] == login_id)
    if login_node.get("depth", -1) != 0:
        print(f"FAIL login depth: {login_node}", file=sys.stderr)
        return False

    child_depths = {
        node.get("depth", -1)
        for node in graph["nodes"]
        if node["endpoint_id"] in {users_id, roles_id, settings_id}
    }
    if child_depths != {1}:
        print(f"FAIL child depths: {child_depths}", file=sys.stderr)
        return False

    if int(analysis.get("max_depth") or 0) < 1:
        print(f"FAIL max_depth: {analysis}", file=sys.stderr)
        return False
    if login_id not in (analysis.get("entry_endpoint_ids") or []):
        print(f"FAIL entry endpoints: {analysis}", file=sys.stderr)
        return False

    print("OK parallel fork, depth levels, flow analysis")
    return True


def _verify_chain_depth() -> bool:
    page_id = str(uuid.uuid4())
    endpoint_ids = [str(uuid.uuid4()) for _ in range(5)]
    endpoints = [
        {
            "endpoint_id": endpoint_ids[index],
            "method": "GET",
            "path": f"/api/step-{index}",
            "path_pattern": f"/api/step-{index}",
            "request_schema": {},
            "response_schema": {},
            "seen_count": 1,
            "risk_score": 10 + index * 5,
        }
        for index in range(5)
    ]
    events = []
    timestamp = 1000.0
    for index, endpoint in enumerate(endpoints):
        events.append(
            {
                "method": "GET",
                "path_pattern": endpoint["path_pattern"],
                "timestamp_ms": timestamp,
            }
        )
        timestamp += 500.0

    graph = build_api_dependency_graph(
        api_endpoints=endpoints,
        network_events_by_page={page_id: events},
    )
    graph = enrich_api_dependency_graph(
        graph,
        api_endpoints=endpoints,
        modules=[],
        auth_intelligence={},
        network_events_by_page={page_id: events},
    )
    analysis = build_api_flow_analysis(graph, endpoints)
    depths = {node.get("depth", -1) for node in graph.get("nodes") or []}
    if max(depths) < 4:
        print(f"FAIL chain max depth: depths={depths}", file=sys.stderr)
        return False
    if int(analysis.get("max_depth") or 0) < 4:
        print(f"FAIL chain analysis max_depth: {analysis}", file=sys.stderr)
        return False

    print("OK acyclic chain depth (5 nodes)")
    return True


def _verify_appmap_integration() -> bool:
    app_id = uuid.uuid4()
    page_id = uuid.uuid4()
    ep1 = uuid.uuid4()
    ep2 = uuid.uuid4()

    session = get_session_factory()()
    try:
        session.add(
            Application(
                app_id=app_id,
                name=f"verify-api-graph-{app_id.hex[:8]}",
                base_url="https://example.com/app/",
            )
        )
        session.add(
            Page(
                page_id=page_id,
                app_id=app_id,
                url="https://example.com/app/users",
                title="Users",
            )
        )
        session.flush()
        session.add(
            ApiEndpoint(
                endpoint_id=ep1,
                app_id=app_id,
                method="GET",
                path="/api/users",
                path_pattern="/api/users",
                source="network",
                first_seen_page_id=page_id,
                seen_page_ids=[str(page_id)],
            )
        )
        session.add(
            ApiEndpoint(
                endpoint_id=ep2,
                app_id=app_id,
                method="POST",
                path="/api/auth/login",
                path_pattern="/api/auth/login",
                source="network",
                first_seen_page_id=page_id,
                seen_page_ids=[str(page_id)],
            )
        )
        session.flush()

        document = load_appmap_for_application(session, app_id)
        if document is None:
            print("FAIL load_appmap_for_application returned None", file=sys.stderr)
            return False
        graph = document.get("api_dependency_graph") or {}
        edges = graph.get("edges") or []
        if len(edges) < 1:
            print(f"FAIL api_dependency_graph edges empty: {graph}", file=sys.stderr)
            return False
        if (document.get("stats") or {}).get("api_dependency_edge_count", 0) < 1:
            print("FAIL stats.api_dependency_edge_count missing", file=sys.stderr)
            return False
        if not isinstance(document.get("api_flow_analysis"), dict):
            print("FAIL api_flow_analysis missing", file=sys.stderr)
            return False
    except Exception:
        session.rollback()
        raise
    finally:
        try:
            session.execute(delete(Application).where(Application.app_id == app_id))
            session.commit()
        except Exception:
            session.rollback()
        session.close()

    print("OK appmap integration (api_dependency_graph, api_flow_analysis, stats)")
    return True


def main() -> int:
    print("verify:api-dependency-graph")
    checks = [
        _verify_graph_rules,
        _verify_parallel_fork_and_depth,
        _verify_chain_depth,
        _verify_appmap_integration,
    ]
    for check in checks:
        if not check():
            return 1
    print("verify:api-dependency-graph OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
