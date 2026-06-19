import logging
from typing import Any

from aqa_celery.agent_runner import (
    run_analyze,
    run_design,
    run_discovery,
    run_execute,
    run_generate_scripts,
)
from aqa_celery.app import app
from aqa_celery.task_names import (
    TASK_ANALYZE,
    TASK_CLEANUP_ARTIFACTS,
    TASK_DESIGN,
    TASK_DISCOVER,
    TASK_EXECUTE,
    TASK_GENERATE_SCRIPTS,
    TASK_REPORT,
)

logger = logging.getLogger(__name__)


def _log_stub_task(task_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Non-agent tasks (execute, report) — stub until Playwright/report workers."""
    pipeline_run_id = payload.get("pipelineRunId", "unknown")
    logger.info(
        "Celery stub task received",
        extra={
            "task": task_name,
            "pipelineRunId": pipeline_run_id,
            "applicationId": payload.get("applicationId"),
        },
    )
    return {"ok": True, "pipelineRunId": pipeline_run_id, "stub": True}


@app.task(name=TASK_DISCOVER, bind=True, max_retries=3)
def discover_task(self, payload: dict[str, Any]) -> dict[str, Any]:
    return run_discovery(payload)


@app.task(name=TASK_DESIGN, bind=True, max_retries=3)
def design_task(self, payload: dict[str, Any]) -> dict[str, Any]:
    return run_design(payload)


@app.task(name=TASK_GENERATE_SCRIPTS, bind=True, max_retries=3)
def generate_scripts_task(self, payload: dict[str, Any]) -> dict[str, Any]:
    return run_generate_scripts(payload)


@app.task(name=TASK_EXECUTE, bind=True, max_retries=3)
def execute_task(self, payload: dict[str, Any]) -> dict[str, Any]:
    return run_execute(payload)


@app.task(name=TASK_REPORT, bind=True, max_retries=3)
def report_task(self, payload: dict[str, Any]) -> dict[str, Any]:
    return _log_stub_task(TASK_REPORT, payload)


@app.task(name=TASK_ANALYZE, bind=True, max_retries=3)
def analyze_task(self, payload: dict[str, Any]) -> dict[str, Any]:
    return run_analyze(payload)


@app.task(name=TASK_CLEANUP_ARTIFACTS, bind=True, max_retries=1)
def cleanup_artifacts_task(self) -> dict[str, Any]:
    from aqa_shared.artifacts.cleanup import cleanup_expired_artifacts, default_retention_days
    from aqa_shared.db.session import get_session_factory

    session = get_session_factory()()
    try:
        deleted = cleanup_expired_artifacts(session)
    finally:
        session.close()
    logger.info(
        "Artifact cleanup finished",
        extra={"deleted": deleted, "retention_days": default_retention_days()},
    )
    return {"ok": True, "deleted": deleted, "retention_days": default_retention_days()}
