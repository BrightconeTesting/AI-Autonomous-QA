"""Test case read services."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aqa_agents.test_design.gherkin import render_feature_file
from aqa_api.schemas.test_cases import TestCaseDetailResponse, TestCaseListResponse, TestCaseSummary
from aqa_shared.db.models import Application, TestCase


def _steps_payload(row: TestCase) -> dict:
    return row.steps if isinstance(row.steps, dict) else {}


def _summary_from_row(row: TestCase) -> TestCaseSummary:
    payload = _steps_payload(row)
    gherkin = payload.get("gherkin") or {}
    machine_steps = payload.get("steps") or []
    return TestCaseSummary(
        testcase_id=row.testcase_id,
        name=row.name,
        priority=row.priority.value if hasattr(row.priority, "value") else str(row.priority),
        status=row.status.value if hasattr(row.status, "value") else str(row.status),
        flow_id=row.flow_id,
        feature=gherkin.get("feature"),
        tags=list(gherkin.get("tags") or []),
        step_count=len(machine_steps),
        created_at=None,
    )


def list_test_cases(db: Session, app_id: UUID) -> TestCaseListResponse:
    rows = list(
        db.scalars(
            select(TestCase).where(TestCase.app_id == app_id).order_by(TestCase.name.asc())
        ).all()
    )
    items = [_summary_from_row(row) for row in rows]
    return TestCaseListResponse(items=items, total=len(items))


def get_test_case(db: Session, testcase_id: UUID) -> TestCaseDetailResponse | None:
    row = db.get(TestCase, testcase_id)
    if row is None:
        return None
    return TestCaseDetailResponse(
        testcase_id=row.testcase_id,
        app_id=row.app_id,
        name=row.name,
        priority=row.priority.value if hasattr(row.priority, "value") else str(row.priority),
        status=row.status.value if hasattr(row.status, "value") else str(row.status),
        flow_id=row.flow_id,
        steps=_steps_payload(row),
        pipeline_run_id=row.pipeline_run_id,
    )


def export_feature_file(db: Session, app_id: UUID) -> str | None:
    app = db.get(Application, app_id)
    if app is None:
        return None
    rows = list(
        db.scalars(
            select(TestCase).where(TestCase.app_id == app_id).order_by(TestCase.name.asc())
        ).all()
    )
    payloads = [_steps_payload(row) for row in rows]
    return render_feature_file(payloads, app_name=app.name)
