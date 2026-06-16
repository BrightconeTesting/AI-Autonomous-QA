#!/usr/bin/env python3
"""Enqueue a discover task via the FastAPI Celery helpers."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from aqa_api.services.celery_enqueue import enqueue_discovery_task
from aqa_shared.celery.types import CeleryTaskPayload

os.environ.setdefault("CELERY_BROKER_URL", os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"))
os.environ.setdefault("CELERY_RESULT_BACKEND", os.getenv("CELERY_RESULT_BACKEND", os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")))


def main() -> int:
    payload = CeleryTaskPayload(
        pipelineRunId="00000000-0000-0000-0000-000000000001",
        applicationId="00000000-0000-0000-0000-000000000002",
        pluginId="ui",
        mode="ui",
    )
    result = enqueue_discovery_task(payload)
    print("verify:celery OK")
    print(
        {
            "taskId": result.task_id,
            "taskName": result.task_name,
            "queue": result.queue,
        }
    )
    return 0 if result.task_id else 1


if __name__ == "__main__":
    sys.exit(main())
