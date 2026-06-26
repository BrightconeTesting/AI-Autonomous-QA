"""Test area decision persistence on discover pipeline runs (Phase E)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from aqa_api.schemas.test_area_decisions import TestAreaDecisionsResponse, UpdateTestAreaDecisionsRequest
from aqa_api.services.appmap_approval import AppMapApprovalError, _latest_completed_discover_run
from aqa_shared.discovery.test_area_decisions import DECISION_APPROVED, DECISION_DISMISSED, normalize_decisions


def get_test_area_decisions(db: Session, application_id: UUID) -> TestAreaDecisionsResponse | None:
    run = _latest_completed_discover_run(db, application_id)
    if run is None:
        return None
    config = dict(run.config or {})
    raw = config.get("recommended_test_area_decisions")
    decisions = normalize_decisions(raw if isinstance(raw, dict) else None)
    return TestAreaDecisionsResponse(
        application_id=application_id,
        pipeline_run_id=run.id,
        decisions=decisions,
    )


def update_test_area_decisions(
    db: Session,
    application_id: UUID,
    body: UpdateTestAreaDecisionsRequest,
) -> TestAreaDecisionsResponse:
    run = _latest_completed_discover_run(db, application_id)
    if run is None:
        raise AppMapApprovalError(
            "No completed discovery run found. Run POST /apps/:id/discover first."
        )
    merged = normalize_decisions(dict(run.config or {}).get("recommended_test_area_decisions"))
    for item in body.decisions:
        area_id = str(item.area_id or "").strip()
        status = str(item.status or "").strip().lower()
        if not area_id:
            continue
        if status not in {DECISION_APPROVED, DECISION_DISMISSED}:
            continue
        merged[area_id] = status
    config = dict(run.config or {})
    config["recommended_test_area_decisions"] = merged
    run.config = config
    db.commit()
    db.refresh(run)
    return TestAreaDecisionsResponse(
        application_id=application_id,
        pipeline_run_id=run.id,
        decisions=merged,
    )
