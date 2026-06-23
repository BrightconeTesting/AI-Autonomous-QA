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
    infer_auth_dependency_edges,
    infer_sequential_edges,
)
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

    print("OK appmap integration (api_dependency_graph, stats.api_dependency_edge_count)")
    return True


def main() -> int:
    print("verify:api-dependency-graph")
    checks = [_verify_graph_rules, _verify_appmap_integration]
    for check in checks:
        if not check():
            return 1
    print("verify:api-dependency-graph OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
