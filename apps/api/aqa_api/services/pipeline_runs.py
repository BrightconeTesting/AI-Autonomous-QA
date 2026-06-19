"""Pipeline run orchestration (Day 13)."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from aqa_api.schemas.pipeline_runs import DiscoverRequest, DiscoverResponse, PipelineRunResponse
from aqa_api.services.celery_enqueue import enqueue_discovery_task
from aqa_shared.celery.types import CeleryTaskPayload
from aqa_shared.db.models import PipelineRun, PipelineStage, PipelineStatus
from aqa_shared.pipeline.cancel import set_pipeline_cancelled
from aqa_shared.pipeline.status import mark_pipeline_failed
from aqa_shared.sse import PipelineEventType, publish_pipeline_event

STALE_PIPELINE_MINUTES = 15


class ActivePipelineConflictError(Exception):
    """Raised when an application already has a pending/running pipeline."""

    def __init__(self, active_run_id: UUID) -> None:
        self.active_run_id = active_run_id
        super().__init__(str(active_run_id))


def _stage_value(stage: PipelineStage | str) -> str:
    return stage.value if isinstance(stage, PipelineStage) else str(stage)


def _status_value(status: PipelineStatus | str) -> str:
    return status.value if isinstance(status, PipelineStatus) else str(status)


def to_pipeline_run_response(run: PipelineRun) -> PipelineRunResponse:
    return PipelineRunResponse(
        pipeline_run_id=run.id,
        application_id=run.application_id,
        status=_status_value(run.status),
        current_stage=_stage_value(run.current_stage),
        config=dict(run.config or {}),
        started_at=run.started_at,
        ended_at=run.ended_at,
        llm_tokens_used=int(run.llm_tokens_used or 0),
        cost_estimate=float(run.cost_estimate or 0),
        error_message=run.error_message,
    )


def to_discover_response(run: PipelineRun) -> DiscoverResponse:
    return DiscoverResponse(
        pipeline_run_id=run.id,
        application_id=run.application_id,
        status=_status_value(run.status),
        current_stage=_stage_value(run.current_stage),
        started_at=run.started_at or datetime.utcnow(),
    )


def find_active_pipeline_run(db: Session, application_id: UUID) -> PipelineRun | None:
    stmt = (
        select(PipelineRun)
        .where(
            PipelineRun.application_id == application_id,
            PipelineRun.status.in_([PipelineStatus.pending, PipelineStatus.running]),
        )
        .order_by(PipelineRun.started_at.desc())
        .limit(1)
    )
    return db.scalars(stmt).first()


def reconcile_stale_active_pipeline(
    db: Session,
    application_id: UUID,
    *,
    max_age_minutes: int = STALE_PIPELINE_MINUTES,
) -> bool:
    """Fail active pipelines older than max_age so new crawls are not blocked forever."""
    active = find_active_pipeline_run(db, application_id)
    if active is None:
        return False
    started = active.started_at or datetime.utcnow()
    if datetime.utcnow() - started <= timedelta(minutes=max_age_minutes):
        return False
    mark_pipeline_failed(
        db,
        active.id,
        error_message=(
            f"Pipeline marked stale after {max_age_minutes} minutes with no completion "
            "(worker stopped or browser disconnected). Safe to start a new crawl."
        ),
    )
    return True


def get_active_pipeline_for_app(db: Session, application_id: UUID) -> PipelineRun | None:
    reconcile_stale_active_pipeline(db, application_id)
    return find_active_pipeline_run(db, application_id)


def get_pipeline_run(db: Session, pipeline_run_id: UUID) -> PipelineRun | None:
    return db.get(PipelineRun, pipeline_run_id)


def cancel_pipeline_run(db: Session, pipeline_run_id: UUID, *, reason: str = "Cancelled by user") -> PipelineRun:
    from aqa_shared.pipeline.status import mark_pipeline_cancelled

    run = db.get(PipelineRun, pipeline_run_id)
    if run is None:
        raise ValueError(f"No pipeline run exists with id {pipeline_run_id}")
    if run.status not in {PipelineStatus.pending, PipelineStatus.running}:
        raise ValueError(f"Pipeline run {pipeline_run_id} is not active")

    mark_pipeline_cancelled(db, pipeline_run_id, reason=reason)
    set_pipeline_cancelled(str(pipeline_run_id))
    publish_pipeline_event(
        str(pipeline_run_id),
        PipelineEventType.pipeline_cancelled,
        {"stage": _stage_value(run.current_stage), "reason": reason},
    )
    db.refresh(run)
    return run


def start_discovery(
    db: Session,
    application_id: UUID,
    body: DiscoverRequest,
) -> PipelineRun:
    reconcile_stale_active_pipeline(db, application_id)
    active = find_active_pipeline_run(db, application_id)
    if active is not None:
        if body.force:
            cancel_pipeline_run(
                db,
                active.id,
                reason="Superseded by a new crawl (force=true)",
            )
        else:
            raise ActivePipelineConflictError(active.id)

    config: dict = {"force": body.force}
    if body.crawl_config_overrides:
        config["crawl_config_overrides"] = body.crawl_config_overrides

    run = PipelineRun(
        application_id=application_id,
        status=PipelineStatus.pending,
        current_stage=PipelineStage.discover,
        config=config,
        started_at=datetime.utcnow(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    payload = CeleryTaskPayload(
        pipelineRunId=str(run.id),
        applicationId=str(application_id),
        pluginId="ui",
        mode="ui",
        crawlConfigOverrides=body.crawl_config_overrides,
    )
    enqueue_discovery_task(payload)
    publish_pipeline_event(
        str(run.id),
        PipelineEventType.stage_started,
        {"stage": PipelineStage.discover.value},
    )
    return run
