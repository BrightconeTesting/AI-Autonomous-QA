"""Execute test scenarios with Playwright (Phase 2)."""

from __future__ import annotations

import logging
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright
from sqlalchemy import select
from sqlalchemy.orm import Session

from aqa_discovery.auth import authenticate_browser, load_auth_config
from aqa_executor.step_handlers import run_step
from aqa_shared.db.models import (
    Application,
    Artifact,
    ArtifactType,
    PipelineStage,
    PipelineStatus,
    Result,
    ResultOutcome,
    TestCase,
    TestRun,
    TestRunStatus,
    TestScript,
)
from aqa_shared.pipeline.cancel import is_pipeline_cancelled
from aqa_shared.pipeline.status import mark_pipeline_completed, mark_pipeline_failed, mark_pipeline_running
from aqa_shared.sse import PipelineEventType, publish_pipeline_event

logger = logging.getLogger(__name__)

EXECUTE_STAGE = PipelineStage.execute.value


def _artifact_root() -> Path:
    return Path(os.getenv("ARTIFACT_STORAGE_PATH", "./artifacts")).resolve()


def _publish(event_type: str, pipeline_run_id: str, data: dict[str, Any]) -> None:
    publish_pipeline_event(pipeline_run_id, event_type, data)


def _sort_cases(cases: list[TestCase]) -> list[TestCase]:
    def sort_key(row: TestCase) -> tuple[int, str]:
        payload = row.steps if isinstance(row.steps, dict) else {}
        destructive = 1 if payload.get("destructive") or payload.get("execution_order") == "last" else 0
        return (destructive, row.name.lower())

    return sorted(cases, key=sort_key)


def execute_pipeline(payload: dict[str, Any]) -> dict[str, Any]:
    pipeline_run_id = payload["pipelineRunId"]
    application_id = uuid.UUID(payload["applicationId"])
    execute_config = payload.get("executeConfig") or {}
    testcase_ids = [uuid.UUID(item) for item in execute_config.get("testcase_ids") or []]
    capture_video = bool(execute_config.get("capture_video", True))

    from aqa_shared.db.session import get_session_factory

    session = get_session_factory()()
    try:
        mark_pipeline_running(session, uuid.UUID(pipeline_run_id), stage=PipelineStage.execute)
        app = session.get(Application, application_id)
        if app is None:
            raise ValueError(f"Application not found: {application_id}")

        run = session.scalar(
            select(TestRun).where(TestRun.pipeline_run_id == uuid.UUID(pipeline_run_id)).limit(1)
        )
        if run is None:
            raise ValueError(f"TestRun not found for pipeline {pipeline_run_id}")

        query = select(TestCase).where(TestCase.app_id == application_id)
        if testcase_ids:
            query = query.where(TestCase.testcase_id.in_(testcase_ids))
        cases = _sort_cases(list(session.scalars(query).all()))
        if not cases:
            raise ValueError("No test cases to execute")

        run.status = TestRunStatus.running
        session.commit()

        passed = failed = 0
        scenario_details: dict[str, dict[str, Any]] = {}
        auth_config = load_auth_config(app.auth_config if isinstance(app.auth_config, dict) else {})
        page_timeout = int((app.crawl_config or {}).get("page_timeout_ms") or 30000)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)

            for index, case in enumerate(cases):
                if is_pipeline_cancelled(pipeline_run_id):
                    raise RuntimeError("Execution cancelled")

                payload_steps = case.steps if isinstance(case.steps, dict) else {}
                gherkin = payload_steps.get("gherkin") or {}
                gherkin_steps = gherkin.get("steps") or []
                machine_steps = payload_steps.get("steps") or []

                _publish(
                    "scenario_started",
                    pipeline_run_id,
                    {
                        "stage": EXECUTE_STAGE,
                        "testcase_id": str(case.testcase_id),
                        "name": case.name,
                        "index": index,
                        "total": len(cases),
                    },
                )

                video_dir = _artifact_root() / "videos" / str(application_id) / str(run.run_id)
                video_dir.mkdir(parents=True, exist_ok=True)
                context_kwargs: dict[str, Any] = {}
                if capture_video:
                    context_kwargs["record_video_dir"] = str(video_dir)
                    context_kwargs["record_video_size"] = {"width": 1280, "height": 720}

                context = browser.new_context(**context_kwargs)
                if auth_config:
                    authenticate_browser(
                        context,
                        auth_config=auth_config,
                        base_url=app.base_url,
                        page_timeout_ms=page_timeout,
                    )

                page = context.new_page()
                scenario_start = time.monotonic()
                outcome = ResultOutcome.passed
                error_msg: str | None = None
                artifact_ids: list[str] = []
                step_results: list[dict[str, Any]] = []
                step_timestamps_ms: list[int] = []

                script = session.scalar(
                    select(TestScript)
                    .where(TestScript.testcase_id == case.testcase_id)
                    .order_by(TestScript.version.desc())
                    .limit(1)
                )

                try:
                    for step_index, step in enumerate(machine_steps):
                        if is_pipeline_cancelled(pipeline_run_id):
                            raise RuntimeError("Execution cancelled")

                        gherkin_step = gherkin_steps[step_index] if step_index < len(gherkin_steps) else {}
                        _publish(
                            "step_started",
                            pipeline_run_id,
                            {
                                "stage": EXECUTE_STAGE,
                                "testcase_id": str(case.testcase_id),
                                "step_index": step_index,
                                "keyword": gherkin_step.get("keyword"),
                                "text": gherkin_step.get("text"),
                            },
                        )
                        step_start = time.monotonic()
                        try:
                            run_step(page, step)
                            step_outcome = "passed"
                        except Exception as exc:
                            step_outcome = "failed"
                            outcome = ResultOutcome.failed
                            error_msg = str(exc)
                            duration_ms = int((time.monotonic() - step_start) * 1000)
                            step_timestamps_ms.append(int((time.monotonic() - scenario_start) * 1000))
                            _publish(
                                "step_completed",
                                pipeline_run_id,
                                {
                                    "stage": EXECUTE_STAGE,
                                    "testcase_id": str(case.testcase_id),
                                    "step_index": step_index,
                                    "outcome": step_outcome,
                                    "duration_ms": duration_ms,
                                    "error": error_msg,
                                },
                            )
                            raise

                        duration_ms = int((time.monotonic() - step_start) * 1000)
                        step_timestamps_ms.append(int((time.monotonic() - scenario_start) * 1000))
                        screenshot_path = (
                            _artifact_root()
                            / "screenshots"
                            / str(application_id)
                            / str(run.run_id)
                            / f"{case.testcase_id}_step_{step_index}.png"
                        )
                        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                        page.screenshot(path=str(screenshot_path))
                        shot = Artifact(
                            run_id=run.run_id,
                            pipeline_run_id=uuid.UUID(pipeline_run_id),
                            type=ArtifactType.screenshot,
                            path=str(screenshot_path),
                            size_bytes=screenshot_path.stat().st_size if screenshot_path.exists() else 0,
                        )
                        session.add(shot)
                        session.flush()
                        artifact_ids.append(str(shot.id))

                        _publish(
                            "step_screenshot",
                            pipeline_run_id,
                            {
                                "stage": EXECUTE_STAGE,
                                "testcase_id": str(case.testcase_id),
                                "step_index": step_index,
                                "artifact_id": str(shot.id),
                            },
                        )
                        _publish(
                            "step_completed",
                            pipeline_run_id,
                            {
                                "stage": EXECUTE_STAGE,
                                "testcase_id": str(case.testcase_id),
                                "step_index": step_index,
                                "outcome": step_outcome,
                                "duration_ms": duration_ms,
                            },
                        )
                        step_results.append(
                            {
                                "index": step_index,
                                "keyword": gherkin_step.get("keyword"),
                                "text": gherkin_step.get("text"),
                                "outcome": step_outcome,
                                "duration_ms": duration_ms,
                            }
                        )
                except Exception:
                    pass
                finally:
                    video_artifact_id: str | None = None
                    context.close()
                    if capture_video:
                        video_files = sorted(video_dir.glob("*.webm"))
                        if video_files:
                            latest = video_files[-1]
                            dest = video_dir / f"{case.testcase_id}.webm"
                            if latest != dest:
                                latest.rename(dest)
                            video = Artifact(
                                run_id=run.run_id,
                                pipeline_run_id=uuid.UUID(pipeline_run_id),
                                type=ArtifactType.video,
                                path=str(dest),
                                size_bytes=dest.stat().st_size if dest.exists() else 0,
                            )
                            session.add(video)
                            session.flush()
                            video_artifact_id = str(video.id)
                            artifact_ids.append(video_artifact_id)

                duration_ms = int((time.monotonic() - scenario_start) * 1000)
                if outcome == ResultOutcome.passed:
                    passed += 1
                else:
                    failed += 1

                if script is not None:
                    session.add(
                        Result(
                            run_id=run.run_id,
                            script_id=script.script_id,
                            assertion=case.name,
                            outcome=outcome,
                            error_msg=error_msg,
                            artifact_ids=artifact_ids,
                        )
                    )

                scenario_details[str(case.testcase_id)] = {
                    "step_timestamps_ms": step_timestamps_ms,
                    "step_results": step_results,
                }

                _publish(
                    "scenario_completed",
                    pipeline_run_id,
                    {
                        "stage": EXECUTE_STAGE,
                        "testcase_id": str(case.testcase_id),
                        "outcome": outcome.value,
                        "duration_ms": duration_ms,
                        "video_artifact_id": video_artifact_id,
                    },
                )
                session.commit()

            browser.close()

        run.status = TestRunStatus.failed if failed else TestRunStatus.passed
        run.ended_at = datetime.utcnow()
        run.summary = {
            "total": len(cases),
            "passed": passed,
            "failed": failed,
            "skipped": 0,
            "scenarios": scenario_details,
        }
        app.last_run_at = datetime.utcnow()
        mark_pipeline_completed(
            session,
            uuid.UUID(pipeline_run_id),
            stage=PipelineStage.execute,
            extra_config={"execute_summary": run.summary},
        )
        session.commit()

        _publish(
            PipelineEventType.stage_completed.value,
            pipeline_run_id,
            {"stage": EXECUTE_STAGE, "duration_ms": 0},
        )
        _publish(PipelineEventType.pipeline_completed.value, pipeline_run_id, {"status": "completed"})

        return {
            "ok": True,
            "pipelineRunId": pipeline_run_id,
            "passed": passed,
            "failed": failed,
        }
    except Exception as exc:
        session.rollback()
        mark_pipeline_failed(session, uuid.UUID(pipeline_run_id), error_message=str(exc))
        run = session.scalar(
            select(TestRun).where(TestRun.pipeline_run_id == uuid.UUID(pipeline_run_id)).limit(1)
        )
        if run is not None:
            run.status = TestRunStatus.error
            run.ended_at = datetime.utcnow()
            session.commit()
        _publish(PipelineEventType.stage_failed.value, pipeline_run_id, {"stage": EXECUTE_STAGE, "error": str(exc)})
        _publish(PipelineEventType.pipeline_completed.value, pipeline_run_id, {"status": "failed"})
        raise
    finally:
        session.close()
