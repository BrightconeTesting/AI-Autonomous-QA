"""Test execution orchestration (Phase 1 — enqueue; worker in Phase 2)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from aqa_api.schemas.execute import ExecuteRequest, ExecuteResponse
from aqa_api.schemas.runs import RunSummary, ScenarioResult, StepResult, TestRunDetailResponse, TestRunListResponse, TestRunSummary
from aqa_api.services.pipeline_runs import ActivePipelineConflictError, find_active_pipeline_run
from aqa_api.services.celery_enqueue import enqueue_execute_task
from aqa_shared.celery.types import CeleryTaskPayload
from aqa_shared.db.models import (
    Artifact,
    ArtifactType,
    PipelineRun,
    PipelineStage,
    PipelineStatus,
    Result,
    ResultOutcome,
    TestCase,
    TestRun,
    TestRunStatus,
    TestScript,
)


class ExecutePreconditionError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def _resolve_testcase_ids(db: Session, app_id: UUID, body: ExecuteRequest) -> list[UUID]:
    if body.retry_from_run_id and body.retry_mode == "failed_only":
        run = db.get(TestRun, body.retry_from_run_id)
        if run is None or run.app_id != app_id:
            raise ExecutePreconditionError("retry_from_run_id not found for this application")
        failed_script_ids = [
            r.script_id
            for r in db.scalars(select(Result).where(Result.run_id == run.run_id)).all()
            if r.outcome == ResultOutcome.failed
        ]
        if not failed_script_ids:
            raise ExecutePreconditionError("No failed scenarios in the referenced run")
        testcase_ids: list[UUID] = []
        for script_id in failed_script_ids:
            script = db.get(TestScript, script_id)
            if script:
                testcase_ids.append(script.testcase_id)
        return testcase_ids

    if body.testcase_ids:
        rows = list(
            db.scalars(
                select(TestCase).where(
                    TestCase.app_id == app_id,
                    TestCase.testcase_id.in_(body.testcase_ids),
                )
            ).all()
        )
        if len(rows) != len(body.testcase_ids):
            raise ExecutePreconditionError("One or more testcase_ids were not found for this application")
        return body.testcase_ids

    rows = list(db.scalars(select(TestCase).where(TestCase.app_id == app_id)).all())
    if not rows:
        raise ExecutePreconditionError("No test cases found. Run POST /apps/:id/generate-tests first.")
    return [row.testcase_id for row in rows]


def start_execute(db: Session, app_id: UUID, body: ExecuteRequest) -> tuple[PipelineRun, TestRun]:
    if not body.force:
        active = find_active_pipeline_run(db, app_id)
        if active is not None:
            raise ActivePipelineConflictError(active.id)

    testcase_ids = _resolve_testcase_ids(db, app_id, body)
    scripts = list(
        db.scalars(
            select(TestScript).where(TestScript.testcase_id.in_(testcase_ids))
        ).all()
    )
    if not scripts:
        raise ExecutePreconditionError("No validated test scripts found for the selected scenarios.")

    config = {
        "testcase_ids": [str(item) for item in testcase_ids],
        "capture_video": body.capture_video,
        "capture_trace": body.capture_trace,
        "force": body.force,
    }
    if body.retry_from_run_id:
        config["retry_from_run_id"] = str(body.retry_from_run_id)
        config["retry_mode"] = body.retry_mode

    pipeline = PipelineRun(
        application_id=app_id,
        status=PipelineStatus.pending,
        current_stage=PipelineStage.execute,
        config=config,
        started_at=datetime.utcnow(),
    )
    db.add(pipeline)
    db.flush()

    test_run = TestRun(
        app_id=app_id,
        pipeline_run_id=pipeline.id,
        status=TestRunStatus.pending,
        started_at=datetime.utcnow(),
        summary={"total": len(testcase_ids), "passed": 0, "failed": 0, "skipped": 0},
    )
    db.add(test_run)
    db.commit()
    db.refresh(pipeline)
    db.refresh(test_run)

    payload = CeleryTaskPayload(
        pipelineRunId=str(pipeline.id),
        applicationId=str(app_id),
        pluginId="ui",
        mode="functional",
        executeConfig=config,
    )
    enqueue_execute_task(payload)
    from aqa_shared.sse import PipelineEventType, publish_pipeline_event

    publish_pipeline_event(
        str(pipeline.id),
        PipelineEventType.stage_started,
        {"stage": PipelineStage.execute.value},
    )
    return pipeline, test_run


def to_execute_response(pipeline: PipelineRun, test_run: TestRun) -> ExecuteResponse:
    return ExecuteResponse(
        pipeline_run_id=pipeline.id,
        application_id=pipeline.application_id,
        test_run_id=test_run.run_id,
        status=pipeline.status.value if hasattr(pipeline.status, "value") else str(pipeline.status),
        current_stage=pipeline.current_stage.value
        if hasattr(pipeline.current_stage, "value")
        else str(pipeline.current_stage),
        started_at=pipeline.started_at or datetime.utcnow(),
    )


def list_runs(db: Session, app_id: UUID) -> TestRunListResponse:
    rows = list(
        db.scalars(
            select(TestRun).where(TestRun.app_id == app_id).order_by(TestRun.started_at.desc())
        ).all()
    )
    items = []
    for row in rows:
        summary_raw = row.summary if isinstance(row.summary, dict) else {}
        items.append(
            TestRunSummary(
                run_id=row.run_id,
                app_id=row.app_id,
                status=row.status.value if hasattr(row.status, "value") else str(row.status),
                started_at=row.started_at,
                ended_at=row.ended_at,
                summary=RunSummary(
                    total=int(summary_raw.get("total") or 0),
                    passed=int(summary_raw.get("passed") or 0),
                    failed=int(summary_raw.get("failed") or 0),
                    skipped=int(summary_raw.get("skipped") or 0),
                ),
            )
        )
    return TestRunListResponse(items=items, total=len(items))


def get_run_detail(db: Session, run_id: UUID) -> TestRunDetailResponse | None:
    run = db.get(TestRun, run_id)
    if run is None:
        return None

    summary_raw = run.summary if isinstance(run.summary, dict) else {}
    scenarios_meta = summary_raw.get("scenarios") if isinstance(summary_raw.get("scenarios"), dict) else {}
    results_rows = list(db.scalars(select(Result).where(Result.run_id == run.run_id)).all())
    scenario_results: list[ScenarioResult] = []

    for result in results_rows:
        script = db.get(TestScript, result.script_id)
        if script is None:
            continue
        case = db.get(TestCase, script.testcase_id)
        if case is None:
            continue
        artifact_ids = result.artifact_ids if isinstance(result.artifact_ids, list) else []
        meta = scenarios_meta.get(str(case.testcase_id)) or {}
        raw_steps = meta.get("step_results") if isinstance(meta.get("step_results"), list) else []
        step_results = [
            StepResult(
                index=int(s.get("index", 0)),
                keyword=s.get("keyword"),
                text=s.get("text"),
                outcome=str(s.get("outcome", "skipped")),
                duration_ms=s.get("duration_ms"),
                error=s.get("error"),
            )
            for s in raw_steps
        ]
        timestamps = meta.get("step_timestamps_ms") if isinstance(meta.get("step_timestamps_ms"), list) else []
        video_id = meta.get("video_artifact_id")
        if not video_id and artifact_ids:
            for aid in artifact_ids:
                artifact = db.get(Artifact, aid)
                if artifact is not None and artifact.type == ArtifactType.video:
                    video_id = str(aid)
                    break
        scenario_results.append(
            ScenarioResult(
                testcase_id=case.testcase_id,
                name=case.name,
                outcome=result.outcome.value if hasattr(result.outcome, "value") else str(result.outcome),
                artifact_ids=[str(item) for item in artifact_ids],
                video_artifact_id=str(video_id) if video_id else None,
                step_results=step_results,
                step_timestamps_ms=[int(t) for t in timestamps],
                error=result.error_msg,
            )
        )

    return TestRunDetailResponse(
        run_id=run.run_id,
        app_id=run.app_id,
        pipeline_run_id=run.pipeline_run_id,
        status=run.status.value if hasattr(run.status, "value") else str(run.status),
        started_at=run.started_at,
        ended_at=run.ended_at,
        summary=RunSummary(
            total=int(summary_raw.get("total") or 0),
            passed=int(summary_raw.get("passed") or 0),
            failed=int(summary_raw.get("failed") or 0),
            skipped=int(summary_raw.get("skipped") or 0),
        ),
        results=scenario_results,
    )
