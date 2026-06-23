"""AppMap approval workflow (DISCOVERY-AGENT-VISION-SPEC §19.3)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from aqa_api.schemas.appmap_approval import AppMapApprovalStatusResponse
from aqa_shared.discovery.approval import APPROVAL_APPROVED, APPROVAL_PENDING, APPROVAL_REJECTED
from aqa_shared.db.models import PipelineRun, PipelineStage, PipelineStatus


class AppMapApprovalError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def _latest_completed_discover_run(db: Session, application_id: UUID) -> PipelineRun | None:
    stmt = (
        select(PipelineRun)
        .where(
            PipelineRun.application_id == application_id,
            PipelineRun.current_stage == PipelineStage.discover,
            PipelineRun.status == PipelineStatus.completed,
        )
        .order_by(PipelineRun.ended_at.desc().nullslast(), PipelineRun.started_at.desc())
        .limit(1)
    )
    return db.scalars(stmt).first()


def get_approval_status(db: Session, application_id: UUID) -> AppMapApprovalStatusResponse:
    run = _latest_completed_discover_run(db, application_id)
    if run is None:
        return AppMapApprovalStatusResponse(
            application_id=application_id,
            pipeline_run_id=None,
            status="none",
        )
    config = dict(run.config or {})
    status = str(config.get("appmap_approval_status") or APPROVAL_PENDING)
    approved_at = config.get("appmap_approved_at")
    if isinstance(approved_at, str):
        try:
            approved_at = datetime.fromisoformat(approved_at.replace("Z", "+00:00"))
        except ValueError:
            approved_at = None
    elif not isinstance(approved_at, datetime):
        approved_at = None
    return AppMapApprovalStatusResponse(
        application_id=application_id,
        pipeline_run_id=run.id,
        status=status,
        approved_at=approved_at,
        rejection_reason=config.get("appmap_rejection_reason"),
    )


def _set_approval(
    db: Session,
    application_id: UUID,
    *,
    status: str,
    rejection_reason: str | None = None,
) -> PipelineRun:
    run = _latest_completed_discover_run(db, application_id)
    if run is None:
        raise AppMapApprovalError(
            "No completed discovery run found. Run POST /apps/:id/discover first."
        )
    config = dict(run.config or {})
    config["appmap_approval_status"] = status
    if status == APPROVAL_APPROVED:
        config["appmap_approved_at"] = datetime.utcnow().isoformat()
        config.pop("appmap_rejection_reason", None)
    elif status == APPROVAL_REJECTED:
        config["appmap_rejection_reason"] = (rejection_reason or "")[:2000]
        config.pop("appmap_approved_at", None)
    run.config = config
    db.commit()
    db.refresh(run)
    return run


def approve_appmap(db: Session, application_id: UUID) -> PipelineRun:
    return _set_approval(db, application_id, status=APPROVAL_APPROVED)


def reject_appmap(db: Session, application_id: UUID, *, reason: str = "") -> PipelineRun:
    return _set_approval(db, application_id, status=APPROVAL_REJECTED, rejection_reason=reason)


def validate_appmap_approved(db: Session, application_id: UUID) -> None:
    status = get_approval_status(db, application_id)
    if status.status == "none":
        raise AppMapApprovalError(
            "No completed discovery run found. Run POST /apps/:id/discover first."
        )
    if status.status != APPROVAL_APPROVED:
        raise AppMapApprovalError(
            "AppMap is pending approval. POST /apps/:id/appmap/approve "
            "or set requireAppmapApproval=false on generate-tests."
        )
