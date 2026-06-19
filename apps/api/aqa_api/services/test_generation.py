"""Test generation orchestration (Phase 1)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from aqa_agents.discovery.appmap import load_appmap_for_application
from aqa_api.schemas.generate_tests import GenerateTestsRequest, GenerateTestsResponse
from aqa_api.services.celery_enqueue import enqueue_generate_tests_tasks
from aqa_api.services.pipeline_runs import ActivePipelineConflictError, find_active_pipeline_run
from aqa_shared.celery.types import CeleryTaskPayload
from aqa_shared.db.models import Application, PipelineRun, PipelineStage, PipelineStatus
from aqa_shared.sse import PipelineEventType, publish_pipeline_event


class AppMapPreconditionError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def validate_appmap_preconditions(
    db: Session,
    application_id: UUID,
    *,
    require_appmap_v2: bool,
) -> dict:
    app = db.get(Application, application_id)
    if app is None:
        raise AppMapPreconditionError(f"No application exists with id {application_id}")

    if app.last_crawl_at is None:
        raise AppMapPreconditionError(
            "No discovery data found. Run POST /apps/:id/discover first."
        )

    appmap = load_appmap_for_application(db, application_id)
    if appmap is None:
        raise AppMapPreconditionError(
            "No discovery data found. Run POST /apps/:id/discover first."
        )

    pages = appmap.get("pages") or []
    flows = appmap.get("flows") or []
    if not pages or not flows:
        raise AppMapPreconditionError(
            "AppMap is empty. Run POST /apps/:id/discover and ensure flows were built."
        )

    if require_appmap_v2:
        schema_version = int(appmap.get("schema_version") or 1)
        stats = appmap.get("stats") or {}
        state_count = int(stats.get("state_count") or 0)
        if schema_version < 2 or state_count < 1:
            raise AppMapPreconditionError(
                "AppMap v2 with CIC state data is required. "
                "Run discovery with enable_cic=true, then rebuild the AppMap."
            )

    return appmap


def to_generate_tests_response(run: PipelineRun) -> GenerateTestsResponse:
    stage = run.current_stage.value if isinstance(run.current_stage, PipelineStage) else str(run.current_stage)
    status = run.status.value if isinstance(run.status, PipelineStatus) else str(run.status)
    return GenerateTestsResponse(
        pipeline_run_id=run.id,
        application_id=run.application_id,
        status=status,
        current_stage=stage,
        started_at=run.started_at or datetime.utcnow(),
    )


def start_generate_tests(
    db: Session,
    application_id: UUID,
    body: GenerateTestsRequest,
) -> PipelineRun:
    if not body.force:
        active = find_active_pipeline_run(db, application_id)
        if active is not None:
            raise ActivePipelineConflictError(active.id)

    validate_appmap_preconditions(
        db,
        application_id,
        require_appmap_v2=body.require_appmap_v2,
    )

    config: dict = {
        "priorities": body.priorities,
        "max_tests": body.max_tests,
        "use_llm": body.use_llm,
        "generate_scripts": body.generate_scripts,
        "require_appmap_v2": body.require_appmap_v2,
        "force": body.force,
    }

    run = PipelineRun(
        application_id=application_id,
        status=PipelineStatus.pending,
        current_stage=PipelineStage.generate_tests,
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
        mode="functional",
        generateConfig=config,
    )
    enqueue_generate_tests_tasks(payload, generate_scripts=body.generate_scripts)
    publish_pipeline_event(
        str(run.id),
        PipelineEventType.stage_started,
        {"stage": PipelineStage.generate_tests.value},
    )
    return run
