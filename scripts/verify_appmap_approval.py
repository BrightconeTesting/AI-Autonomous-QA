#!/usr/bin/env python3
"""Verify AppMap approval workflow API (M0)."""

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
from aqa_shared.db.models import (  # noqa: E402
    Application,
    Flow,
    FlowSource,
    Page,
    PageState,
    PipelineRun,
    PipelineStage,
    PipelineStatus,
)
from aqa_shared.db.session import get_session_factory  # noqa: E402
from aqa_shared.discovery.approval import APPROVAL_PENDING  # noqa: E402


def _cleanup(session, app_id: uuid.UUID) -> None:
    from aqa_shared.db.models import Element, StateTransition, TestCase

    session.query(TestCase).filter(TestCase.app_id == app_id).delete()
    session.query(PipelineRun).filter(PipelineRun.application_id == app_id).delete()
    session.query(StateTransition).filter(StateTransition.app_id == app_id).delete()
    session.query(Flow).filter(Flow.app_id == app_id).delete()
    session.query(Element).filter(
        Element.page_id.in_(session.query(Page.page_id).filter(Page.app_id == app_id))
    ).delete(synchronize_session=False)
    session.query(PageState).filter(
        PageState.page_id.in_(session.query(Page.page_id).filter(Page.app_id == app_id))
    ).delete(synchronize_session=False)
    session.query(Page).filter(Page.app_id == app_id).delete()
    session.query(Application).filter(Application.app_id == app_id).delete()
    session.commit()


def _seed_discover_run(session, app_id: uuid.UUID) -> uuid.UUID:
    page = Page(app_id=app_id, url="https://example.com/app/home", title="Home")
    session.add(page)
    session.flush()
    session.add(
        PageState(page_id=page.page_id, state_key="baseline", fingerprint="fp1", interaction_depth=0)
    )
    session.add(
        Flow(
            app_id=app_id,
            name="Home flow",
            sequence=[{"action": "navigate", "page_id": str(page.page_id), "url": page.url}],
            source=FlowSource.crawler,
        )
    )
    run_id = uuid.uuid4()
    session.add(
        PipelineRun(
            id=run_id,
            application_id=app_id,
            status=PipelineStatus.completed,
            current_stage=PipelineStage.discover,
            config={"appmap_approval_status": APPROVAL_PENDING},
            started_at=datetime.utcnow(),
            ended_at=datetime.utcnow(),
        )
    )
    app_row = session.get(Application, app_id)
    assert app_row is not None
    app_row.last_crawl_at = datetime.utcnow()
    session.commit()
    return run_id


def main() -> int:
    print("verify:appmap-approval")
    client = TestClient(app)
    session = get_session_factory()()
    app_id = uuid.uuid4()

    try:
        session.add(
            Application(
                app_id=app_id,
                name="Approval Verify App",
                base_url="https://example.com/app/",
            )
        )
        session.commit()

        blocked = client.post(f"/api/v1/apps/{app_id}/generate-tests", json={"requireAppmapV2": False})
        if blocked.status_code != 422:
            print(f"FAIL blocked without discovery: {blocked.status_code}", file=sys.stderr)
            return 1

        _seed_discover_run(session, app_id)
        pending = client.post(f"/api/v1/apps/{app_id}/generate-tests", json={"requireAppmapV2": False})
        if pending.status_code != 422 or "approval" not in pending.json().get("detail", "").lower():
            print(f"FAIL pending approval gate: {pending.status_code} {pending.text}", file=sys.stderr)
            return 1
        print("OK generate-tests blocked when AppMap pending approval")

        status = client.get(f"/api/v1/apps/{app_id}/appmap/approval")
        if status.status_code != 200 or status.json()["status"] != APPROVAL_PENDING:
            print(f"FAIL approval status: {status.status_code} {status.text}", file=sys.stderr)
            return 1

        approved = client.post(f"/api/v1/apps/{app_id}/appmap/approve")
        if approved.status_code != 200 or approved.json()["status"] != "approved":
            print(f"FAIL approve: {approved.status_code} {approved.text}", file=sys.stderr)
            return 1

        accepted = client.post(
            f"/api/v1/apps/{app_id}/generate-tests",
            json={"force": True, "requireAppmapV2": False},
        )
        if accepted.status_code != 202:
            print(f"FAIL generate after approve: {accepted.status_code} {accepted.text}", file=sys.stderr)
            return 1
        print("OK generate-tests allowed after approval")
    finally:
        _cleanup(session, app_id)
        session.close()

    print("verify:appmap-approval OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
