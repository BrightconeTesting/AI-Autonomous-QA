"""Pipeline run status helpers for generate / execute stages."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from aqa_shared.db.models import PipelineRun, PipelineStage, PipelineStatus


def mark_pipeline_running(
    db: Session,
    pipeline_run_id: uuid.UUID,
    *,
    stage: PipelineStage,
) -> None:
    run = db.get(PipelineRun, pipeline_run_id)
    if run is None:
        raise ValueError(f"Pipeline run not found: {pipeline_run_id}")
    run.status = PipelineStatus.running
    run.current_stage = stage
    if run.started_at is None:
        run.started_at = datetime.utcnow()
    db.commit()


def mark_pipeline_stage_completed(
    db: Session,
    pipeline_run_id: uuid.UUID,
    *,
    stage: PipelineStage,
    extra_config: dict | None = None,
) -> None:
    run = db.get(PipelineRun, pipeline_run_id)
    if run is None:
        raise ValueError(f"Pipeline run not found: {pipeline_run_id}")
    run.current_stage = stage
    if extra_config:
        config = dict(run.config or {})
        config.update(extra_config)
        run.config = config
    db.commit()


def mark_pipeline_completed(
    db: Session,
    pipeline_run_id: uuid.UUID,
    *,
    stage: PipelineStage | None = None,
    extra_config: dict | None = None,
) -> None:
    run = db.get(PipelineRun, pipeline_run_id)
    if run is None:
        raise ValueError(f"Pipeline run not found: {pipeline_run_id}")
    run.status = PipelineStatus.completed
    if stage is not None:
        run.current_stage = stage
    run.ended_at = datetime.utcnow()
    run.error_message = None
    if extra_config:
        config = dict(run.config or {})
        config.update(extra_config)
        run.config = config
    db.commit()


def mark_pipeline_failed(
    db: Session,
    pipeline_run_id: uuid.UUID,
    *,
    error_message: str,
) -> None:
    run = db.get(PipelineRun, pipeline_run_id)
    if run is None:
        return
    run.status = PipelineStatus.failed
    run.error_message = error_message[:2000]
    run.ended_at = datetime.utcnow()
    db.commit()


def mark_pipeline_cancelled(
    db: Session,
    pipeline_run_id: uuid.UUID,
    *,
    reason: str = "Cancelled by user",
) -> None:
    run = db.get(PipelineRun, pipeline_run_id)
    if run is None:
        raise ValueError(f"Pipeline run not found: {pipeline_run_id}")
    run.status = PipelineStatus.cancelled
    run.error_message = reason[:2000]
    run.ended_at = datetime.utcnow()
    db.commit()
