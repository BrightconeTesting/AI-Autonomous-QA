#!/usr/bin/env python3
"""Complete E2E QA: API discover -> Celery worker -> DB persist -> SSE (Day 19)."""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
os.environ.setdefault("DATABASE_URL", "postgresql://aqa:aqa@localhost:5432/autonomous_qa")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

from fastapi.testclient import TestClient  # noqa: E402

from aqa_api.main import app as fastapi_app  # noqa: E402
from aqa_celery.agent_runner import run_discovery  # noqa: E402
from aqa_shared.celery.types import CeleryTaskPayload  # noqa: E402
from aqa_shared.db.models import (  # noqa: E402
    Application,
    Artifact,
    ArtifactType,
    Element,
    Page,
    PipelineRun,
    PipelineStatus,
)
from aqa_shared.db.session import get_session_factory  # noqa: E402
from aqa_shared.sse import list_pipeline_events  # noqa: E402

ORANGEHRM_APP_ID = "30b005f1-baee-4e01-9ae6-6886c7b44022"
POLL_TIMEOUT_SEC = 300
POLL_INTERVAL_SEC = 3


def _fail(msg: str) -> int:
    print(f"FAIL {msg}", file=sys.stderr)
    return 1


def _ok(msg: str) -> None:
    print(f"OK {msg}")


def _ensure_orangehrm_credentials() -> None:
    if not os.getenv("ORANGEHRM_DEMO_USER", "").strip():
        os.environ["ORANGEHRM_DEMO_USER"] = json.dumps(
            {"username": "Admin", "password": "admin123"}
        )


def _wait_pipeline_terminal(pipeline_run_id: str, *, timeout_sec: int = POLL_TIMEOUT_SEC) -> PipelineRun | None:
    session = get_session_factory()()
    deadline = time.monotonic() + timeout_sec
    try:
        while time.monotonic() < deadline:
            run = session.get(PipelineRun, uuid.UUID(pipeline_run_id))
            if run is None:
                return None
            if run.status in (PipelineStatus.completed, PipelineStatus.failed):
                session.refresh(run)
                return run
            session.expire(run)
            time.sleep(POLL_INTERVAL_SEC)
        return session.get(PipelineRun, uuid.UUID(pipeline_run_id))
    finally:
        session.close()


def _count_persisted(app_id: uuid.UUID, pipeline_run_id: uuid.UUID) -> dict:
    session = get_session_factory()()
    try:
        pages = session.query(Page).filter(Page.app_id == app_id).count()
        elements = (
            session.query(Element).join(Page).filter(Page.app_id == app_id).count()
        )
        artifacts = (
            session.query(Artifact)
            .filter(
                Artifact.pipeline_run_id == pipeline_run_id,
                Artifact.type == ArtifactType.screenshot,
            )
            .count()
        )
        app = session.get(Application, app_id)
        return {
            "pages": pages,
            "elements": elements,
            "artifacts": artifacts,
            "last_crawl_at": app.last_crawl_at if app else None,
        }
    finally:
        session.close()


def verify_api_discover_e2e() -> bool:
    """POST discover -> worker processes -> DB + SSE updated."""
    _ensure_orangehrm_credentials()
    client = TestClient(fastapi_app)

    resp = client.post(
        f"/api/v1/apps/{ORANGEHRM_APP_ID}/discover",
        json={
            "force": True,
            "crawl_config_overrides": {
                "max_pages": 3,
                "max_depth": 1,
                "respect_robots_txt": False,
            },
        },
    )
    if resp.status_code != 202:
        print(f"FAIL discover API status={resp.status_code} body={resp.text}", file=sys.stderr)
        return False

    body = resp.json()
    pipeline_run_id = body["pipeline_run_id"]
    _ok(f"POST /apps/{{id}}/discover -> 202 pipeline_run_id={pipeline_run_id}")

    # Execute the same task body the Celery worker runs (avoids stale-worker code drift).
    payload = CeleryTaskPayload(
        pipelineRunId=pipeline_run_id,
        applicationId=ORANGEHRM_APP_ID,
        pluginId="ui",
        mode="ui",
        crawlConfigOverrides={
            "max_pages": 3,
            "max_depth": 1,
            "respect_robots_txt": False,
        },
    ).to_worker_dict()
    print("Running discovery pipeline synchronously (Day 19 code path)...")
    task_result = run_discovery(payload)
    if not task_result.get("ok"):
        print(f"FAIL run_discovery: {task_result}", file=sys.stderr)
        return False
    _ok(f"run_discovery completed: pages={len(task_result.get('output', {}).get('discovery_worker', {}).get('pages', []))}")

    run = _wait_pipeline_terminal(pipeline_run_id, timeout_sec=10)
    if run is None:
        print("FAIL pipeline run not found after discover", file=sys.stderr)
        return False
    if run.status != PipelineStatus.completed:
        print(
            f"FAIL pipeline status={run.status} error={run.error_message}",
            file=sys.stderr,
        )
        return False
    _ok(f"pipeline_runs.status=completed (ended_at={run.ended_at})")

    stats = (run.config or {}).get("discovery_stats", {})
    if not stats.get("page_count"):
        print(f"FAIL missing discovery_stats in pipeline config: {run.config}", file=sys.stderr)
        return False
    _ok(f"pipeline config discovery_stats: {stats}")

    app_id = uuid.UUID(ORANGEHRM_APP_ID)
    counts = _count_persisted(app_id, uuid.UUID(pipeline_run_id))
    if counts["pages"] < 1:
        print(f"FAIL no pages in DB: {counts}", file=sys.stderr)
        return False
    if counts["elements"] < 1:
        print(f"FAIL no elements in DB: {counts}", file=sys.stderr)
        return False
    if counts["artifacts"] < 1:
        print(f"FAIL no screenshot artifacts: {counts}", file=sys.stderr)
        return False
    if counts["last_crawl_at"] is None:
        print("FAIL applications.last_crawl_at not set", file=sys.stderr)
        return False
    _ok(
        f"DB persist: pages={counts['pages']} elements={counts['elements']} "
        f"artifacts={counts['artifacts']} last_crawl_at set"
    )

    session = get_session_factory()()
    try:
        sample_page = (
            session.query(Page)
            .filter(Page.app_id == app_id)
            .order_by(Page.discovered_at.desc())
            .first()
        )
        if sample_page and sample_page.screenshot_path:
            if not Path(sample_page.screenshot_path).is_file():
                print(f"FAIL screenshot missing: {sample_page.screenshot_path}", file=sys.stderr)
                return False
            _ok(f"screenshot file exists: {Path(sample_page.screenshot_path).name}")
        sample_element = (
            session.query(Element)
            .join(Page)
            .filter(Page.app_id == app_id)
            .first()
        )
        if sample_element is None or not (
            sample_element.semantic_selector or sample_element.xpath_fallback
        ):
            print("FAIL element missing locator", file=sys.stderr)
            return False
        _ok(
            f"sample element locator: "
            f"{(sample_element.semantic_selector or sample_element.xpath_fallback)[:60]}"
        )
    finally:
        session.close()

    events = list_pipeline_events(pipeline_run_id)
    event_types = [e.event.value if hasattr(e.event, "value") else str(e.event) for e in events]
    if "stage_started" not in event_types:
        print(f"FAIL SSE missing stage_started: {event_types}", file=sys.stderr)
        return False
    if "stage_progress" not in event_types:
        print(f"FAIL SSE missing stage_progress: {event_types}", file=sys.stderr)
        return False
    if "stage_completed" not in event_types:
        print(f"FAIL SSE missing stage_completed: {event_types}", file=sys.stderr)
        return False
    _ok(f"SSE events: {', '.join(event_types)}")

    get_resp = client.get(f"/api/v1/pipeline-runs/{pipeline_run_id}")
    if get_resp.status_code != 200 or get_resp.json()["status"] != "completed":
        print(f"FAIL GET pipeline-runs: {get_resp.status_code} {get_resp.text}", file=sys.stderr)
        return False
    _ok("GET /pipeline-runs/{id} returns completed")

    app_resp = client.get(f"/api/v1/apps/{ORANGEHRM_APP_ID}")
    if app_resp.status_code != 200:
        print(f"FAIL GET app: {app_resp.status_code}", file=sys.stderr)
        return False
    if app_resp.json().get("last_crawl_at") is None:
        print("FAIL app API last_crawl_at is null", file=sys.stderr)
        return False
    _ok("GET /apps/{id} shows last_crawl_at")

    return True


def main() -> int:
    print("verify:e2e-discovery")
    print("=" * 50)
    print("Prerequisite: PostgreSQL + Redis running")
    print("  (Celery worker optional — test runs discovery code synchronously)")
    print("=" * 50)

    if not verify_api_discover_e2e():
        return 1

    print("=" * 50)
    print("verify:e2e-discovery OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
