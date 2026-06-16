"""Celery task enqueue helpers for the FastAPI orchestrator."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from aqa_celery.tasks import (
    analyze_task,
    design_task,
    discover_task,
    execute_task,
    generate_scripts_task,
    report_task,
)
from aqa_shared.celery.task_names import (
    CELERY_TASK_ANALYZE,
    CELERY_TASK_DESIGN,
    CELERY_TASK_DISCOVER,
    CELERY_TASK_EXECUTE,
    CELERY_TASK_GENERATE_SCRIPTS,
    CELERY_TASK_REPORT,
    CELERY_TASK_ROUTES,
)
from aqa_shared.celery.types import CeleryTaskPayload

logger = logging.getLogger(__name__)

CELERY_ENQUEUE_RETRY = {
    "max_retries": 3,
    "retry_backoff": True,
    "retry_backoff_max_seconds": 600,
    "retry_jitter": True,
}


@dataclass(frozen=True)
class EnqueueResult:
    task_id: str
    task_name: str
    queue: str


def _enqueue(task_fn, task_name: str, payload: CeleryTaskPayload) -> EnqueueResult:
    queue = CELERY_TASK_ROUTES[task_name]
    async_result = task_fn.apply_async(args=[payload.to_worker_dict()], queue=queue)
    logger.info(
        "Celery task enqueued",
        extra={
            "celeryTask": task_name,
            "queue": queue,
            "taskId": async_result.id,
            "pipelineRunId": payload.pipeline_run_id,
            "applicationId": payload.application_id,
        },
    )
    return EnqueueResult(task_id=async_result.id, task_name=task_name, queue=queue)


def enqueue_discovery_task(payload: CeleryTaskPayload) -> EnqueueResult:
    return _enqueue(discover_task, CELERY_TASK_DISCOVER, payload)


def enqueue_design_task(payload: CeleryTaskPayload) -> EnqueueResult:
    return _enqueue(design_task, CELERY_TASK_DESIGN, payload)


def enqueue_generate_scripts_task(payload: CeleryTaskPayload) -> EnqueueResult:
    return _enqueue(generate_scripts_task, CELERY_TASK_GENERATE_SCRIPTS, payload)


def enqueue_execute_task(payload: CeleryTaskPayload) -> EnqueueResult:
    return _enqueue(execute_task, CELERY_TASK_EXECUTE, payload)


def enqueue_report_task(payload: CeleryTaskPayload) -> EnqueueResult:
    return _enqueue(report_task, CELERY_TASK_REPORT, payload)


def enqueue_analyze_task(payload: CeleryTaskPayload) -> EnqueueResult:
    return _enqueue(analyze_task, CELERY_TASK_ANALYZE, payload)
