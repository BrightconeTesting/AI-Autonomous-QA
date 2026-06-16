#!/usr/bin/env python3
"""E2E: FastAPI enqueue -> Celery worker -> result backend (Day 9)."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ.setdefault("CELERY_BROKER_URL", os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"))
os.environ.setdefault("CELERY_RESULT_BACKEND", os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"))

from celery.result import AsyncResult

from aqa_api.services.celery_enqueue import (
    enqueue_analyze_task,
    enqueue_design_task,
    enqueue_discovery_task,
    enqueue_execute_task,
    enqueue_generate_scripts_task,
    enqueue_report_task,
)
from aqa_celery.app import app
from aqa_shared.celery.types import CeleryTaskPayload

PAYLOAD = CeleryTaskPayload(
    pipelineRunId="00000000-0000-0000-0000-000000000001",
    applicationId="00000000-0000-0000-0000-000000000002",
    pluginId="ui",
    mode="ui",
)

TASKS = [
    ("discover", enqueue_discovery_task, "agentId"),
    ("design", enqueue_design_task, "agentId"),
    ("generate_scripts", enqueue_generate_scripts_task, "agentId"),
    ("execute", enqueue_execute_task, "stub"),
    ("report", enqueue_report_task, "stub"),
    ("analyze", enqueue_analyze_task, "agentId"),
]


def main() -> int:
    print("verify:e2e-celery")
    for label, fn, expect in TASKS:
        r = fn(PAYLOAD)
        ar = AsyncResult(r.task_id, app=app)
        try:
            result = ar.get(timeout=15)
        except Exception as exc:
            print(f"FAIL {label}: {exc}", file=sys.stderr)
            return 1
        if ar.status != "SUCCESS":
            print(f"FAIL {label}: status={ar.status}", file=sys.stderr)
            return 1
        if expect == "agentId" and "agentId" not in result:
            print(f"FAIL {label}: missing agentId in {result}", file=sys.stderr)
            return 1
        if expect == "stub" and not result.get("stub"):
            print(f"FAIL {label}: expected stub result", file=sys.stderr)
            return 1
        detail = result.get("agentId") or "stub"
        print(f"OK {label}: SUCCESS {detail}")

    print("verify:e2e-celery OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
