#!/usr/bin/env python3
"""Verify pipeline cancel endpoint — DASHBOARD-SPEC §19."""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi.testclient import TestClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ.setdefault("DATABASE_URL", os.getenv("DATABASE_URL", ""))

from aqa_api.main import app  # noqa: E402
from aqa_shared.db.models import Application, PipelineRun, PipelineStage, PipelineStatus  # noqa: E402
from aqa_shared.db.session import get_session_factory  # noqa: E402


def main() -> int:
    print("verify:cancel-pipeline")
    client = TestClient(app)
    session = get_session_factory()()
    app_id = uuid.uuid4()
    pipeline_id = uuid.uuid4()

    try:
        session.add(Application(app_id=app_id, name="Cancel Test App", base_url="https://example.com/"))
        session.add(
            PipelineRun(
                id=pipeline_id,
                application_id=app_id,
                status=PipelineStatus.running,
                current_stage=PipelineStage.discover,
                started_at=datetime.utcnow(),
            )
        )
        session.commit()

        cancel = client.post(f"/api/v1/pipeline-runs/{pipeline_id}/cancel", json={})
        if cancel.status_code != 202:
            print(f"FAIL cancel: {cancel.status_code} {cancel.text}", file=sys.stderr)
            return 1
        body = cancel.json()
        if body.get("status") != "cancelled":
            print(f"FAIL cancel status: {body}", file=sys.stderr)
            return 1
        print("OK POST /pipeline-runs/{id}/cancel returns cancelled")

        session.refresh(session.get(PipelineRun, pipeline_id))
        row = session.get(PipelineRun, pipeline_id)
        if row is None or row.status != PipelineStatus.cancelled:
            print("FAIL DB status not cancelled", file=sys.stderr)
            return 1
        print("OK pipeline run persisted as cancelled")

        again = client.post(f"/api/v1/pipeline-runs/{pipeline_id}/cancel", json={})
        if again.status_code != 409:
            print(f"FAIL double cancel expected 409, got {again.status_code}", file=sys.stderr)
            return 1
        print("OK cancel inactive pipeline returns 409")

    finally:
        session.query(PipelineRun).filter(PipelineRun.application_id == app_id).delete()
        session.query(Application).filter(Application.app_id == app_id).delete()
        session.commit()
        session.close()

    print("verify:cancel-pipeline OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
