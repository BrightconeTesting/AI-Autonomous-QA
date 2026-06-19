#!/usr/bin/env python3
"""Verify retry failed-only execute — DASHBOARD-SPEC §19."""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from dotenv import load_dotenv
from fastapi.testclient import TestClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ.setdefault("DATABASE_URL", os.getenv("DATABASE_URL", ""))

from aqa_api.main import app  # noqa: E402
from aqa_shared.db.models import (  # noqa: E402
    Application,
    PipelineRun,
    PipelineStage,
    PipelineStatus,
    Result,
    ResultOutcome,
    TestCase,
    TestCaseStatus,
    TestPriority,
    TestRun,
    TestRunStatus,
    TestScript,
)
from aqa_shared.db.session import get_session_factory  # noqa: E402


def _cleanup(session, app_id: uuid.UUID) -> None:
    run_ids = [r.run_id for r in session.query(TestRun).filter(TestRun.app_id == app_id).all()]
    for run_id in run_ids:
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
    print("verify:retry-failed")
    client = TestClient(app)
    session = get_session_factory()()
    app_id = uuid.uuid4()
    case_pass = uuid.uuid4()
    case_fail = uuid.uuid4()
    script_pass = uuid.uuid4()
    script_fail = uuid.uuid4()
    prior_run_id = uuid.uuid4()

    try:
        session.add(Application(app_id=app_id, name="Retry Failed App", base_url="https://example.com/"))
        session.add(
            TestCase(
                testcase_id=case_pass,
                app_id=app_id,
                name="Pass case",
                priority=TestPriority.high,
                status=TestCaseStatus.draft,
                steps={"steps": []},
            )
        )
        session.add(
            TestCase(
                testcase_id=case_fail,
                app_id=app_id,
                name="Fail case",
                priority=TestPriority.high,
                status=TestCaseStatus.draft,
                steps={"steps": []},
            )
        )
        session.add(TestScript(script_id=script_pass, testcase_id=case_pass, version=1, code="// pass"))
        session.add(TestScript(script_id=script_fail, testcase_id=case_fail, version=1, code="// fail"))
        session.add(
            TestRun(
                run_id=prior_run_id,
                app_id=app_id,
                status=TestRunStatus.failed,
                started_at=datetime.utcnow(),
                summary={"total": 2, "passed": 1, "failed": 1, "skipped": 0},
            )
        )
        session.add(
            Result(
                run_id=prior_run_id,
                script_id=script_pass,
                assertion="Pass case",
                outcome=ResultOutcome.passed,
            )
        )
        session.add(
            Result(
                run_id=prior_run_id,
                script_id=script_fail,
                assertion="Fail case",
                outcome=ResultOutcome.failed,
                error_msg="assertion failed",
            )
        )
        session.commit()

        with patch("aqa_api.services.test_execution.enqueue_execute_task") as mock_enqueue:
            mock_enqueue.return_value = None
            resp = client.post(
                f"/api/v1/apps/{app_id}/execute",
                json={
                    "testcase_ids": [],
                    "retry_from_run_id": str(prior_run_id),
                    "retry_mode": "failed_only",
                    "force": True,
                },
            )

        if resp.status_code != 202:
            print(f"FAIL execute retry: {resp.status_code} {resp.text}", file=sys.stderr)
            return 1

        if not mock_enqueue.called:
            print("FAIL enqueue_execute_task not called", file=sys.stderr)
            return 1

        payload = mock_enqueue.call_args[0][0]
        ids = (payload.execute_config or {}).get("testcase_ids") or []
        if ids != [str(case_fail)]:
            print(f"FAIL retry testcase_ids expected failed only, got {ids}", file=sys.stderr)
            return 1
        print("OK retry failed_only enqueues failed testcase only")

        bad = client.post(
            f"/api/v1/apps/{app_id}/execute",
            json={
                "retry_from_run_id": str(uuid.uuid4()),
                "retry_mode": "failed_only",
                "force": True,
            },
        )
        if bad.status_code != 422:
            print(f"FAIL missing run should 422, got {bad.status_code}", file=sys.stderr)
            return 1
        print("OK invalid retry_from_run_id returns 422")

    finally:
        _cleanup(session, app_id)
        session.close()

    print("verify:retry-failed OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
