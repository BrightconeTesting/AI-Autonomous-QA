#!/usr/bin/env python3
"""Full discovery smoke: register -> discover -> AppMap (Day 20 sprint exit)."""

from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ.setdefault("DATABASE_URL", "postgresql://aqa:aqa@localhost:5432/autonomous_qa")

from aqa_celery.agent_runner import run_discovery  # noqa: E402
from aqa_shared.celery.types import CeleryTaskPayload  # noqa: E402
from aqa_shared.db.models import Artifact, ArtifactType, Flow, PipelineRun, PipelineStatus  # noqa: E402
from aqa_shared.db.session import get_session_factory  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aqa_api.main import app  # noqa: E402

POLL_TIMEOUT_SEC = 30


def main() -> int:
    print("verify:smoke-discovery")
    client = TestClient(app)

    app_name = f"Smoke Discovery {uuid.uuid4().hex[:8]}"
    create_resp = client.post(
        "/api/v1/apps",
        json={
            "name": app_name,
            "base_url": "https://example.com",
            "crawl_config": {
                "max_pages": 1,
                "max_depth": 1,
                "respect_robots_txt": False,
            },
        },
    )
    if create_resp.status_code != 201:
        print(f"FAIL register app: {create_resp.status_code} {create_resp.text}", file=sys.stderr)
        return 1
    app_id = create_resp.json()["app_id"]
    print(f"OK POST /apps: app_id={app_id}")

    discover_resp = client.post(
        f"/api/v1/apps/{app_id}/discover",
        json={"force": True, "crawl_config_overrides": {"max_pages": 1, "max_depth": 1}},
    )
    if discover_resp.status_code != 202:
        print(f"FAIL discover: {discover_resp.status_code}", file=sys.stderr)
        return 1
    pipeline_run_id = discover_resp.json()["pipeline_run_id"]
    print(f"OK POST /apps/{{id}}/discover: pipeline_run_id={pipeline_run_id}")

    payload = CeleryTaskPayload(
        pipelineRunId=pipeline_run_id,
        applicationId=app_id,
        pluginId="ui",
        mode="ui",
        crawlConfigOverrides={"max_pages": 1, "max_depth": 1, "respect_robots_txt": False},
    ).to_worker_dict()
    result = run_discovery(payload)
    if not result.get("ok"):
        print(f"FAIL run_discovery: {result}", file=sys.stderr)
        return 1

    output = result.get("output") or {}
    stats = output.get("stats") or {}
    if stats.get("page_count", 0) < 1:
        print(f"FAIL DiscoveryAgent stats: {stats}", file=sys.stderr)
        return 1
    if stats.get("flow_count", 0) < 1:
        print(f"FAIL DiscoveryAgent produced no flows: {stats}", file=sys.stderr)
        return 1
    print(
        f"OK run_discovery: pages={stats.get('page_count')} "
        f"elements={stats.get('element_count')} flows={stats.get('flow_count')}"
    )

    session = get_session_factory()()
    try:
        run = session.get(PipelineRun, uuid.UUID(pipeline_run_id))
        if run is None or run.status != PipelineStatus.completed:
            print(f"FAIL pipeline status: {run.status if run else None}", file=sys.stderr)
            return 1
        flow_count = session.query(Flow).filter(Flow.app_id == uuid.UUID(app_id)).count()
        if flow_count < 1:
            print(f"FAIL flows in DB: {flow_count}", file=sys.stderr)
            return 1
        appmap_artifacts = (
            session.query(Artifact)
            .filter(
                Artifact.pipeline_run_id == uuid.UUID(pipeline_run_id),
                Artifact.type == ArtifactType.appmap,
            )
            .count()
        )
        if appmap_artifacts < 1:
            print("FAIL appmap artifact row missing", file=sys.stderr)
            return 1
        print(f"OK DB: flows={flow_count} appmap_artifacts={appmap_artifacts}")
    finally:
        session.close()

    appmap_resp = client.get(f"/api/v1/apps/{app_id}/appmap")
    if appmap_resp.status_code != 200:
        print(f"FAIL GET appmap: {appmap_resp.status_code}", file=sys.stderr)
        return 1
    appmap = appmap_resp.json()
    if appmap["stats"]["page_count"] < 1 or appmap["stats"]["flow_count"] < 1:
        print(f"FAIL appmap response stats: {appmap['stats']}", file=sys.stderr)
        return 1
    print(
        f"OK GET /apps/{{id}}/appmap: pages={appmap['stats']['page_count']} "
        f"flows={appmap['stats']['flow_count']}"
    )

    print("verify:smoke-discovery OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
