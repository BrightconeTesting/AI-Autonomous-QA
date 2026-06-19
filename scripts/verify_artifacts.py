#!/usr/bin/env python3
"""Verify artifact GET stream + DELETE — DASHBOARD-SPEC §19."""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from fastapi.testclient import TestClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ.setdefault("DATABASE_URL", os.getenv("DATABASE_URL", ""))

from aqa_api.main import app  # noqa: E402
from aqa_shared.artifacts.cleanup import cleanup_expired_artifacts  # noqa: E402
from aqa_shared.db.models import Application, Artifact, ArtifactType, TestRun, TestRunStatus  # noqa: E402
from aqa_shared.db.session import get_session_factory  # noqa: E402


def main() -> int:
    print("verify:artifacts")
    client = TestClient(app)
    session = get_session_factory()()
    app_id = uuid.uuid4()
    run_id = uuid.uuid4()
    artifact_id = uuid.uuid4()
    tmp = Path("artifacts/_verify") / str(artifact_id)
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(b"verify-artifact-content")

    try:
        session.add(
            Application(
                app_id=app_id,
                name="Verify Artifacts",
                base_url="https://example.com/",
            )
        )
        session.add(
            TestRun(
                run_id=run_id,
                app_id=app_id,
                status=TestRunStatus.passed,
                started_at=datetime.utcnow(),
            )
        )
        session.add(
            Artifact(
                id=artifact_id,
                run_id=run_id,
                type=ArtifactType.video,
                path=str(tmp.resolve()),
                size_bytes=tmp.stat().st_size,
            )
        )
        session.commit()

        stream = client.get(f"/api/v1/artifacts/{artifact_id}")
        if stream.status_code != 200 or stream.content != b"verify-artifact-content":
            print(f"FAIL GET artifact stream: {stream.status_code}", file=sys.stderr)
            return 1
        print("OK GET /artifacts/{id} streams file")

        meta = client.get(f"/api/v1/artifacts/{artifact_id}/meta")
        if meta.status_code != 200 or meta.json().get("type") != "video":
            print(f"FAIL GET meta: {meta.text}", file=sys.stderr)
            return 1
        print("OK GET /artifacts/{id}/meta")

        delete = client.delete(f"/api/v1/artifacts/{artifact_id}")
        if delete.status_code != 204:
            print(f"FAIL DELETE: {delete.status_code}", file=sys.stderr)
            return 1
        if tmp.exists():
            print("FAIL file still on disk", file=sys.stderr)
            return 1
        print("OK DELETE /artifacts/{id}")

        old_id = uuid.uuid4()
        old_path = Path("artifacts/_verify") / str(old_id)
        old_path.write_bytes(b"old")
        session.add(
            Artifact(
                id=old_id,
                run_id=run_id,
                type=ArtifactType.screenshot,
                path=str(old_path.resolve()),
                size_bytes=1,
            )
        )
        session.flush()
        old_row = session.get(Artifact, old_id)
        assert old_row is not None
        old_row.created_at = datetime.utcnow() - timedelta(days=60)
        session.commit()
        deleted = cleanup_expired_artifacts(session, retention_days=30)
        if deleted < 1 or old_path.exists():
            print(f"FAIL cleanup_expired_artifacts deleted={deleted}", file=sys.stderr)
            return 1
        print(f"OK cleanup_expired_artifacts deleted={deleted}")

    finally:
        session.query(Artifact).filter(Artifact.run_id == run_id).delete()
        session.query(TestRun).filter(TestRun.app_id == app_id).delete()
        session.query(Application).filter(Application.app_id == app_id).delete()
        session.commit()
        session.close()

    print("verify:artifacts OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
