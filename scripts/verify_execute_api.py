#!/usr/bin/env python3
"""Verify Playwright execute worker — Phase 2."""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ["ENCRYPTION_KEY"] = os.getenv("ENCRYPTION_KEY") or ("0123456789abcdef" * 4)
os.environ.setdefault("DATABASE_URL", os.getenv("DATABASE_URL", ""))

from aqa_executor.runner import execute_pipeline  # noqa: E402
from aqa_shared.db.models import (  # noqa: E402
    Application,
    PipelineRun,
    PipelineStage,
    PipelineStatus,
    Result,
    TestCase,
    TestCaseStatus,
    TestPriority,
    TestRun,
    TestRunStatus,
    TestScript,
)
from aqa_shared.db.session import get_session_factory  # noqa: E402
from aqa_agents.test_design.gherkin import attach_gherkin


def _fixture_url() -> str:
    fixture = (
        Path(__file__).resolve().parents[1]
        / "workers/discovery_worker/tests/fixtures/cic/modal.html"
    ).resolve()
    return fixture.as_uri()


def _cleanup(session, app_id: uuid.UUID) -> None:
    from aqa_shared.db.models import Artifact

    run_ids = [r.run_id for r in session.query(TestRun).filter(TestRun.app_id == app_id).all()]
    for run_id in run_ids:
        session.query(Artifact).filter(Artifact.run_id == run_id).delete()
        session.query(Result).filter(Result.run_id == run_id).delete()
    session.query(TestRun).filter(TestRun.app_id == app_id).delete()
    session.query(TestScript).filter(
        TestScript.testcase_id.in_(session.query(TestCase.testcase_id).filter(TestCase.app_id == app_id))
    ).delete(synchronize_session=False)
    session.query(TestCase).filter(TestCase.app_id == app_id).delete()
    session.query(PipelineRun).filter(PipelineRun.application_id == app_id).delete()
    session.query(Application).filter(Application.app_id == app_id).delete()
    session.commit()


def main() -> int:
    print("verify:execute")
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            p.chromium.launch(headless=True).close()
    except Exception as exc:
        print(f"SKIP playwright unavailable: {exc}", file=sys.stderr)
        return 0

    session = get_session_factory()()
    app_id = uuid.uuid4()
    pipeline_id = uuid.uuid4()
    run_id = uuid.uuid4()
    case_id = uuid.uuid4()
    script_id = uuid.uuid4()
    fixture_url = _fixture_url()

    machine_steps = [
        {"action": "navigate", "target": fixture_url},
        {"action": "assertVisible", "target": "#open-modal"},
    ]
    case_dict = {
        "name": "Open modal fixture",
        "priority": "high",
        "flow_id": None,
        "destructive": False,
        "execution_order": "default",
        "steps": machine_steps,
    }
    steps_payload = attach_gherkin(case_dict, app_name="Fixture App")

    try:
        session.add(
            Application(
                app_id=app_id,
                name="Execute Verify App",
                base_url=fixture_url,
                last_crawl_at=datetime.utcnow(),
            )
        )
        session.add(
            PipelineRun(
                id=pipeline_id,
                application_id=app_id,
                status=PipelineStatus.pending,
                current_stage=PipelineStage.execute,
                config={"testcase_ids": [str(case_id)]},
                started_at=datetime.utcnow(),
            )
        )
        session.add(
            TestCase(
                testcase_id=case_id,
                app_id=app_id,
                pipeline_run_id=pipeline_id,
                name=case_dict["name"],
                steps=steps_payload,
                priority=TestPriority.high,
                status=TestCaseStatus.draft,
            )
        )
        session.add(
            TestScript(
                script_id=script_id,
                testcase_id=case_id,
                code='{"manifest_version":1,"steps":[]}',
                validated_at=datetime.utcnow(),
            )
        )
        session.add(
            TestRun(
                run_id=run_id,
                app_id=app_id,
                pipeline_run_id=pipeline_id,
                status=TestRunStatus.pending,
                started_at=datetime.utcnow(),
                summary={"total": 1, "passed": 0, "failed": 0, "skipped": 0},
            )
        )
        session.commit()

        result = execute_pipeline(
            {
                "pipelineRunId": str(pipeline_id),
                "applicationId": str(app_id),
                "executeConfig": {
                    "testcase_ids": [str(case_id)],
                    "capture_video": False,
                },
            }
        )
        if not result.get("ok"):
            print(f"FAIL execute_pipeline: {result}", file=sys.stderr)
            return 1

        run = session.get(TestRun, run_id)
        if run is None or run.status != TestRunStatus.passed:
            print(f"FAIL run status: {run.status if run else None}", file=sys.stderr)
            return 1

        results = session.query(Result).filter(Result.run_id == run_id).all()
        if len(results) != 1 or results[0].outcome.value != "passed":
            print(f"FAIL results: {results}", file=sys.stderr)
            return 1

        print("OK execute_pipeline passed fixture scenario")
    finally:
        _cleanup(session, app_id)
        session.close()

    print("verify:execute OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
