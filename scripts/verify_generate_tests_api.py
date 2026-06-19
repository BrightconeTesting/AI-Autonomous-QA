#!/usr/bin/env python3
"""Verify generate-tests endpoint — Phase 1."""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import select

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
)
from aqa_shared.db.session import get_session_factory  # noqa: E402


def _cleanup(session, app_id: uuid.UUID, pipeline_run_ids: list[uuid.UUID]) -> None:
    from aqa_shared.db.models import Artifact, Element, StateTransition, TestCase, TestScript

    for run_id in pipeline_run_ids:
        session.query(TestCase).filter(TestCase.pipeline_run_id == run_id).delete()
        session.query(Artifact).filter(Artifact.pipeline_run_id == run_id).delete()
        session.query(PipelineRun).filter(PipelineRun.id == run_id).delete()
    session.query(TestScript).filter(
        TestScript.testcase_id.in_(session.query(TestCase.testcase_id).filter(TestCase.app_id == app_id))
    ).delete(synchronize_session=False)
    session.query(TestCase).filter(TestCase.app_id == app_id).delete()
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


def _seed_v1_appmap(session, app_id: uuid.UUID) -> None:
    page = Page(
        app_id=app_id,
        url="https://example.com/app/dashboard",
        title="Dashboard",
    )
    session.add(page)
    session.flush()
    session.add(
        Flow(
            app_id=app_id,
            name="Dashboard flow",
            description="Navigate-only flow",
            sequence=[
                {
                    "action": "navigate",
                    "page_id": str(page.page_id),
                    "url": page.url,
                    "title": page.title,
                }
            ],
            source=FlowSource.crawler,
        )
    )
    app_row = session.get(Application, app_id)
    assert app_row is not None
    app_row.last_crawl_at = datetime.utcnow()
    session.commit()


def _seed_v2_appmap(session, app_id: uuid.UUID) -> None:
    page = session.scalars(select(Page).where(Page.app_id == app_id).limit(1)).first()
    if page is None:
        _seed_v1_appmap(session, app_id)
        page = session.scalars(select(Page).where(Page.app_id == app_id).limit(1)).first()
    assert page is not None
    existing = session.scalars(
        select(PageState).where(PageState.page_id == page.page_id, PageState.state_key == "baseline")
    ).first()
    if existing is None:
        session.add(
            PageState(
                page_id=page.page_id,
                state_key="baseline",
                fingerprint="abc123",
                interaction_depth=0,
            )
        )
        session.commit()


def main() -> int:
    print("verify:generate-tests")
    client = TestClient(app)
    session = get_session_factory()()
    app_id = uuid.uuid4()
    pipeline_run_ids: list[uuid.UUID] = []

    try:
        session.add(
            Application(
                app_id=app_id,
                name="Verify Generate Tests App",
                base_url="https://example.com/app/",
            )
        )
        session.commit()

        missing = client.post(f"/api/v1/apps/{app_id}/generate-tests", json={})
        if missing.status_code != 422:
            print(f"FAIL empty app: expected 422 got {missing.status_code}", file=sys.stderr)
            return 1
        print("OK generate-tests without discovery returns 422")

        _seed_v1_appmap(session, app_id)
        v1_only = client.post(f"/api/v1/apps/{app_id}/generate-tests", json={})
        if v1_only.status_code != 422:
            print(f"FAIL v1 appmap: expected 422 got {v1_only.status_code}", file=sys.stderr)
            return 1
        print("OK generate-tests rejects AppMap v1 by default")

        _seed_v2_appmap(session, app_id)
        accepted = client.post(
            f"/api/v1/apps/{app_id}/generate-tests",
            json={"force": True, "requireAppmapV2": False},
        )
        if accepted.status_code != 202:
            print(f"FAIL generate-tests: expected 202 got {accepted.status_code} {accepted.text}", file=sys.stderr)
            return 1
        pipeline_run_ids.append(uuid.UUID(accepted.json()["pipeline_run_id"]))
        print("OK POST /apps/{id}/generate-tests returns 202")
    finally:
        _cleanup(session, app_id, pipeline_run_ids)
        session.close()

    print("verify:generate-tests OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
