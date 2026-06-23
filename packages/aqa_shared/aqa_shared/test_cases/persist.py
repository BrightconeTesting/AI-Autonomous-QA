"""Persist generated test cases and scripts to PostgreSQL."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from aqa_shared.db.models import TestCase, TestCaseStatus, TestPriority, TestScript


def _parse_priority(value: str | None) -> TestPriority:
    try:
        return TestPriority(str(value or "medium"))
    except ValueError:
        return TestPriority.medium


def _parse_flow_id(value: Any) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def persist_test_cases(
    db: Session,
    *,
    app_id: uuid.UUID,
    pipeline_run_id: uuid.UUID,
    test_cases: list[dict[str, Any]],
    steps_payloads: list[dict[str, Any]],
) -> list[TestCase]:
    rows: list[TestCase] = []
    for case, payload in zip(test_cases, steps_payloads, strict=True):
        row = TestCase(
            app_id=app_id,
            pipeline_run_id=pipeline_run_id,
            flow_id=_parse_flow_id(case.get("flow_id")),
            name=str(case.get("name") or "Unnamed scenario")[:255],
            description=None,
            steps=payload,
            priority=_parse_priority(case.get("priority")),
            status=TestCaseStatus.draft,
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def persist_test_scripts_for_pipeline(db: Session, *, pipeline_run_id: uuid.UUID) -> int:
    cases = list(
        db.scalars(select(TestCase).where(TestCase.pipeline_run_id == pipeline_run_id)).all()
    )
    count = 0
    for case in cases:
        existing = db.scalar(
            select(TestScript)
            .where(TestScript.testcase_id == case.testcase_id)
            .order_by(TestScript.version.desc())
            .limit(1)
        )
        if existing is not None:
            continue
        steps_data = case.steps if isinstance(case.steps, dict) else {}
        machine_steps = steps_data.get("steps") or []
        manifest = {
            "manifest_version": 1,
            "framework": "playwright",
            "testcase_id": str(case.testcase_id),
            "steps": machine_steps,
        }
        db.add(
            TestScript(
                testcase_id=case.testcase_id,
                code=json.dumps(manifest, separators=(",", ":")),
                validated_at=datetime.utcnow(),
            )
        )
        count += 1
    db.flush()
    return count
