#!/usr/bin/env python3
"""Verify Gherkin .feature export syntax — DASHBOARD-SPEC §19."""

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
from aqa_agents.test_design.gherkin import attach_gherkin  # noqa: E402
from aqa_celery.agent_runner import run_design, run_generate_scripts  # noqa: E402
from aqa_shared.db.models import Application, Flow, FlowSource, Page, PageState, PipelineRun, PipelineStage, PipelineStatus, TestCase  # noqa: E402
from aqa_shared.db.session import get_session_factory  # noqa: E402
from aqa_shared.test_cases.persist import persist_test_cases  # noqa: E402


def _seed(session, app_id: uuid.UUID) -> None:
    page = Page(app_id=app_id, url="https://example.com/app/home", title="Home")
    session.add(page)
    session.flush()
    session.add(PageState(page_id=page.page_id, state_key="baseline", fingerprint="fp", interaction_depth=0))
    session.add(
        Flow(
            app_id=app_id,
            name="Home flow",
            sequence=[{"action": "navigate", "url": page.url}],
            source=FlowSource.crawler,
        )
    )
    app_row = session.get(Application, app_id)
    assert app_row is not None
    app_row.last_crawl_at = datetime.utcnow()
    session.commit()


def _cleanup(session, app_id: uuid.UUID) -> None:
    from aqa_shared.db.models import Element, PipelineRun, TestScript

    session.query(TestScript).filter(
        TestScript.testcase_id.in_(session.query(TestCase.testcase_id).filter(TestCase.app_id == app_id))
    ).delete(synchronize_session=False)
    session.query(TestCase).filter(TestCase.app_id == app_id).delete()
    session.query(PipelineRun).filter(PipelineRun.application_id == app_id).delete()
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


def main() -> int:
    print("verify:gherkin-export")
    client = TestClient(app)
    session = get_session_factory()()
    app_id = uuid.uuid4()

    try:
        session.add(Application(app_id=app_id, name="Gherkin Export App", base_url="https://example.com/app/"))
        session.commit()
        _seed(session, app_id)

        cases = [
            {
                "name": "Navigate home",
                "priority": "high",
                "steps": [{"action": "navigate", "target": "https://example.com/app/home"}],
            }
        ]
        pipeline_run_id = uuid.uuid4()
        session.add(
            PipelineRun(
                id=pipeline_run_id,
                application_id=app_id,
                status=PipelineStatus.completed,
                current_stage=PipelineStage.generate_scripts,
            )
        )
        session.flush()
        payloads = [attach_gherkin(c, app_name="Gherkin Export App") for c in cases]
        persist_test_cases(
            session,
            app_id=app_id,
            pipeline_run_id=pipeline_run_id,
            test_cases=cases,
            steps_payloads=payloads,
        )
        session.commit()

        export = client.get(f"/api/v1/apps/{app_id}/test-cases/export.feature")
        if export.status_code != 200:
            print(f"FAIL export: {export.status_code}", file=sys.stderr)
            return 1
        body = export.text
        for token in ("Feature:", "Scenario:", "Given"):
            if token not in body:
                print(f"FAIL export missing {token!r}: {body[:200]}", file=sys.stderr)
                return 1
        print("OK export.feature contains valid Gherkin keywords")

        count = len(session.scalars(select(TestCase).where(TestCase.app_id == app_id)).all())
        if not count:
            print("FAIL no test cases persisted", file=sys.stderr)
            return 1
        print("OK scenarios persisted with gherkin")

    finally:
        _cleanup(session, app_id)
        session.close()

    print("verify:gherkin-export OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
