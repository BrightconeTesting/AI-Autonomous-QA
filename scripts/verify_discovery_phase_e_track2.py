#!/usr/bin/env python3
"""Verify Phase E Track 2 — test area decisions and SPA crawl helpers."""

from __future__ import annotations

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

from aqa_api.main import app  # noqa: E402
from aqa_discovery.spa_routes import spa_urls_for_enqueue  # noqa: E402
from aqa_discovery.types import SpaRouteEvent  # noqa: E402
from aqa_shared.db.models import Application, PipelineRun, PipelineStage, PipelineStatus  # noqa: E402
from aqa_shared.db.session import get_session_factory  # noqa: E402
from aqa_shared.discovery.test_area_decisions import (  # noqa: E402
    DECISION_DISMISSED,
    apply_test_area_decisions,
    normalize_decisions,
)


def _verify_test_area_decisions_unit() -> bool:
    appmap = {
        "recommended_test_areas": [
            {"area_id": "a1", "area": "Form validation"},
            {"area_id": "a2", "area": "API contract"},
        ]
    }
    filtered = apply_test_area_decisions(appmap, {"a2": DECISION_DISMISSED})
    kept = filtered.get("recommended_test_areas") or []
    if len(kept) != 1 or kept[0].get("area_id") != "a1":
        print(f"FAIL apply_test_area_decisions: {kept}", file=sys.stderr)
        return False
    if normalize_decisions({"a1": "approved", "bad": "unknown"}).get("bad"):
        print("FAIL normalize_decisions should ignore invalid status", file=sys.stderr)
        return False
    print("OK test area decisions (filter dismissed areas)")
    return True


def _verify_test_area_decisions_api() -> bool:
    session_factory = get_session_factory()
    app_id = uuid.uuid4()
    run_id = uuid.uuid4()
    with session_factory() as session:
        session.add(
            Application(
                app_id=app_id,
                name="Track2 verify app",
                base_url="https://example.com/app/",
            )
        )
        session.add(
            PipelineRun(
                id=run_id,
                application_id=app_id,
                status=PipelineStatus.completed,
                current_stage=PipelineStage.discover,
                config={},
                started_at=datetime.utcnow(),
                ended_at=datetime.utcnow(),
            )
        )
        session.commit()

    client = TestClient(app)
    put_resp = client.put(
        f"/api/v1/apps/{app_id}/appmap/test-area-decisions",
        json={"decisions": [{"area_id": "area-1", "status": "dismissed"}]},
    )
    if put_resp.status_code != 200:
        print(f"FAIL PUT test-area-decisions status={put_resp.status_code}", file=sys.stderr)
        return False
    get_resp = client.get(f"/api/v1/apps/{app_id}/appmap/test-area-decisions")
    payload = get_resp.json()
    if payload.get("decisions", {}).get("area-1") != "dismissed":
        print(f"FAIL GET test-area-decisions payload={payload}", file=sys.stderr)
        return False

    with session_factory() as session:
        session.query(PipelineRun).filter(PipelineRun.application_id == app_id).delete()
        session.query(Application).filter(Application.app_id == app_id).delete()
        session.commit()

    print("OK test area decisions API")
    return True


def _verify_spa_enqueue_helper() -> bool:
    events = [
        SpaRouteEvent(
            from_url="https://example.com/app/",
            to_url="https://example.com/app/users",
            discovery_method="pushstate_listener",
            source_page_url="https://example.com/app/",
        ),
        SpaRouteEvent(
            from_url="https://example.com/app/users",
            to_url="https://example.com/app/users",
            discovery_method="pushstate_listener",
            source_page_url="https://example.com/app/",
        ),
    ]
    urls = spa_urls_for_enqueue(events)
    if urls != ["https://example.com/app/users"]:
        print(f"FAIL spa_urls_for_enqueue dedupe: {urls}", file=sys.stderr)
        return False
    print("OK spa_urls_for_enqueue")
    return True


def main() -> int:
    print("verify:discovery-phase-e-track2")
    ok = (
        _verify_test_area_decisions_unit()
        and _verify_test_area_decisions_api()
        and _verify_spa_enqueue_helper()
    )
    if not ok:
        return 1
    print("verify:discovery-phase-e-track2 OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
