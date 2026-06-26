#!/usr/bin/env python3
"""Verify Phase E — AppMap diff between pipeline runs."""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi.testclient import TestClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ["ENCRYPTION_KEY"] = os.getenv("ENCRYPTION_KEY") or ("0123456789abcdef" * 4)
os.environ.setdefault("DATABASE_URL", os.getenv("DATABASE_URL", ""))

from aqa_agents.discovery.appmap import appmap_artifact_path  # noqa: E402
from aqa_agents.discovery.appmap_diff import compute_appmap_diff  # noqa: E402
from aqa_api.main import app  # noqa: E402
from aqa_shared.db.models import Application, PipelineRun, PipelineStage, PipelineStatus  # noqa: E402
from aqa_shared.db.session import get_session_factory  # noqa: E402


def _verify_unit_diff() -> bool:
    page_a = str(uuid.uuid4())
    page_b = str(uuid.uuid4())
    module_a = "users"
    from_doc = {
        "pages": [{"page_id": page_a, "url": "https://example.com/app/users", "title": "Users"}],
        "elements": [{"page_id": page_a}, {"page_id": page_a}],
        "modules": [
            {
                "module_id": module_a,
                "name": "Users",
                "pages": [page_a],
                "flow_ids": [],
                "risk_score": 40,
            }
        ],
        "api_endpoints": [
            {
                "endpoint_id": str(uuid.uuid4()),
                "method": "GET",
                "path": "/api/users",
                "path_pattern": "/api/users",
            }
        ],
        "discovery_completeness_score": 45,
        "scoring_summary": {"app_risk_score": 30},
    }
    to_doc = {
        "pages": [
            {"page_id": page_a, "url": "https://example.com/app/users", "title": "User management"},
            {"page_id": page_b, "url": "https://example.com/app/settings", "title": "Settings"},
        ],
        "elements": [{"page_id": page_a}, {"page_id": page_a}, {"page_id": page_a}, {"page_id": page_b}],
        "modules": [
            {
                "module_id": module_a,
                "name": "Users",
                "pages": [page_a],
                "flow_ids": ["flow-1"],
                "risk_score": 55,
            },
            {
                "module_id": "settings",
                "name": "Settings",
                "pages": [page_b],
                "flow_ids": [],
            },
        ],
        "api_endpoints": [
            {
                "endpoint_id": str(uuid.uuid4()),
                "method": "GET",
                "path": "/api/users",
                "path_pattern": "/api/users",
            },
            {
                "endpoint_id": str(uuid.uuid4()),
                "method": "POST",
                "path": "/api/settings",
                "path_pattern": "/api/settings",
            },
        ],
        "api_dependency_graph": {
            "edges": [
                {
                    "from_endpoint_id": "ep-1",
                    "to_endpoint_id": "ep-2",
                    "edge_type": "sequential",
                    "confidence": 0.8,
                }
            ]
        },
        "discovery_completeness_score": 62,
        "scoring_summary": {"app_risk_score": 48},
    }

    diff = compute_appmap_diff(from_doc, to_doc)
    if diff.get("unchanged"):
        print("FAIL expected diff to report changes", file=sys.stderr)
        return False
    if len(diff["pages"]["added"]) != 1:
        print(f"FAIL pages.added={diff['pages']['added']}", file=sys.stderr)
        return False
    if not diff["pages"]["changed"]:
        print("FAIL expected changed page metadata", file=sys.stderr)
        return False
    if diff["elements"]["delta_by_page"][0]["delta"] != 1:
        print(f"FAIL element delta={diff['elements']['delta_by_page']}", file=sys.stderr)
        return False
    if len(diff["api_endpoints"]["added"]) != 1:
        print(f"FAIL api added={diff['api_endpoints']['added']}", file=sys.stderr)
        return False
    if len(diff["modules"]["added"]) != 1:
        print(f"FAIL modules added={diff['modules']['added']}", file=sys.stderr)
        return False
    if diff["scores"]["discovery_completeness_score"]["delta"] != 17:
        print(f"FAIL score delta={diff['scores']}", file=sys.stderr)
        return False

    print("OK compute_appmap_diff (pages, elements, apis, modules, scores)")
    return True


def _write_artifact(run_id: uuid.UUID, document: dict) -> Path:
    path = appmap_artifact_path(run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return path


def _verify_api_diff() -> bool:
    session_factory = get_session_factory()
    app_id = uuid.uuid4()
    from_run_id = uuid.uuid4()
    to_run_id = uuid.uuid4()
    page_id = str(uuid.uuid4())

    from_doc = {
        "application_id": str(app_id),
        "schema_version": 3,
        "pages": [{"page_id": page_id, "url": "https://example.com/app/home", "title": "Home"}],
        "elements": [],
        "flows": [],
        "modules": [],
        "discovery_completeness_score": 40,
    }
    to_doc = {
        **from_doc,
        "pages": [{"page_id": page_id, "url": "https://example.com/app/home", "title": "Home updated"}],
        "discovery_completeness_score": 55,
    }

    with session_factory() as session:
        session.add(
            Application(
                app_id=app_id,
                name="Diff verify app",
                base_url="https://example.com/app/",
            )
        )
        from_path = _write_artifact(from_run_id, from_doc)
        to_path = _write_artifact(to_run_id, to_doc)
        session.add(
            PipelineRun(
                id=from_run_id,
                application_id=app_id,
                status=PipelineStatus.completed,
                current_stage=PipelineStage.discover,
                config={
                    "appmap_hash": "hash-from",
                    "appmap_path": str(from_path),
                    "discovery_stats": {"page_count": 1},
                },
                started_at=datetime.utcnow(),
                ended_at=datetime.utcnow(),
            )
        )
        session.add(
            PipelineRun(
                id=to_run_id,
                application_id=app_id,
                status=PipelineStatus.completed,
                current_stage=PipelineStage.discover,
                config={
                    "appmap_hash": "hash-to",
                    "appmap_path": str(to_path),
                    "discovery_stats": {"page_count": 1},
                },
                started_at=datetime.utcnow(),
                ended_at=datetime.utcnow(),
            )
        )
        session.commit()

    client = TestClient(app)
    list_resp = client.get(f"/api/v1/apps/{app_id}/discover-runs")
    if list_resp.status_code != 200:
        print(f"FAIL discover-runs status={list_resp.status_code}", file=sys.stderr)
        return False
    items = list_resp.json().get("items") or []
    if len(items) != 2:
        print(f"FAIL discover-runs count={len(items)}", file=sys.stderr)
        return False

    diff_resp = client.get(
        f"/api/v1/apps/{app_id}/appmap/diff",
        params={"from_run": str(from_run_id), "to_run": str(to_run_id)},
    )
    if diff_resp.status_code != 200:
        print(f"FAIL appmap/diff status={diff_resp.status_code} {diff_resp.text}", file=sys.stderr)
        return False
    payload = diff_resp.json()
    if payload.get("unchanged"):
        print("FAIL API diff reported unchanged", file=sys.stderr)
        return False
    if not payload.get("pages", {}).get("changed"):
        print(f"FAIL API diff pages.changed={payload.get('pages')}", file=sys.stderr)
        return False
    if payload.get("scores", {}).get("discovery_completeness_score", {}).get("delta") != 15:
        print(f"FAIL API score delta={payload.get('scores')}", file=sys.stderr)
        return False

    with session_factory() as session:
        session.query(PipelineRun).filter(PipelineRun.application_id == app_id).delete()
        session.query(Application).filter(Application.app_id == app_id).delete()
        session.commit()

    print("OK GET /apps/{id}/discover-runs + /appmap/diff API")
    return True


def main() -> int:
    print("verify:appmap-diff")
    ok = _verify_unit_diff() and _verify_api_diff()
    if not ok:
        return 1
    print("verify:appmap-diff OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
