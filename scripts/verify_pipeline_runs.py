#!/usr/bin/env python3
"""Verify pipeline runs + discover endpoint — Day 13."""

import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import select

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ["ENCRYPTION_KEY"] = os.getenv("ENCRYPTION_KEY") or ("0123456789abcdef" * 4)
os.environ.setdefault("DATABASE_URL", os.getenv("DATABASE_URL", ""))

from aqa_api.main import app
from aqa_shared.db.models import PipelineRun
from aqa_shared.db.session import get_session_factory

APP_PAYLOAD = {
    "name": "Verify Pipeline App",
    "base_url": "https://juice-shop.herokuapp.com",
    "seed_urls": [],
    "crawl_config": {"max_pages": 5},
}


def main() -> int:
    print("verify:pipeline")
    client = TestClient(app)

    create = client.post("/api/v1/apps", json=APP_PAYLOAD)
    if create.status_code != 201:
        print(f"FAIL create app: {create.status_code} {create.text}", file=sys.stderr)
        return 1
    app_id = create.json()["app_id"]

    discover = client.post(
        f"/api/v1/apps/{app_id}/discover",
        json={"force": False, "crawl_config_overrides": {"max_pages": 5}},
    )
    if discover.status_code != 202:
        print(f"FAIL discover: {discover.status_code} {discover.text}", file=sys.stderr)
        return 1

    body = discover.json()
    pipeline_run_id = body.get("pipeline_run_id") or body.get("pipelineRunId")
    if not pipeline_run_id:
        print(f"FAIL discover response missing pipeline_run_id: {body}", file=sys.stderr)
        return 1
    if body.get("status") != "pending" or body.get("current_stage") != "discover":
        print(f"FAIL discover response shape: {body}", file=sys.stderr)
        return 1
    print(f"OK POST /apps/{{id}}/discover: pipeline_run_id={pipeline_run_id}")

    session = get_session_factory()()
    try:
        row = session.scalar(
            select(PipelineRun).where(PipelineRun.id == uuid.UUID(pipeline_run_id))
        )
        if row is None:
            print("FAIL pipeline_runs row not in DB", file=sys.stderr)
            return 1
        if str(row.application_id) != app_id:
            print("FAIL pipeline_runs application_id mismatch", file=sys.stderr)
            return 1
        print("OK pipeline_runs row created before enqueue")
    finally:
        session.close()

    status = client.get(f"/api/v1/pipeline-runs/{pipeline_run_id}")
    if status.status_code != 200:
        print(f"FAIL GET pipeline-runs: {status.status_code}", file=sys.stderr)
        return 1
    if status.json().get("status") != "pending":
        print(f"FAIL pipeline status: {status.json()}", file=sys.stderr)
        return 1
    print("OK GET /pipeline-runs/{id}")

    conflict = client.post(f"/api/v1/apps/{app_id}/discover", json={})
    if conflict.status_code != 409:
        print(f"FAIL concurrent discover: expected 409 got {conflict.status_code}", file=sys.stderr)
        return 1
    if not conflict.json().get("active_pipeline_run_id"):
        print(f"FAIL 409 missing active_pipeline_run_id: {conflict.json()}", file=sys.stderr)
        return 1
    print("OK concurrent discover returns 409 Conflict")

    missing_app = client.post(f"/api/v1/apps/{uuid.uuid4()}/discover", json={})
    if missing_app.status_code != 404:
        print(f"FAIL discover unknown app: expected 404 got {missing_app.status_code}", file=sys.stderr)
        return 1
    print("OK discover unknown app returns 404")

    print("verify:pipeline OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
