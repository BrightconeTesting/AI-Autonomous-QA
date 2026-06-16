#!/usr/bin/env python3
"""Verify Celery tasks invoke Day 8 agent stubs (Day 9)."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

os.environ.setdefault("CELERY_BROKER_URL", os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"))
os.environ.setdefault("CELERY_RESULT_BACKEND", os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"))

from aqa_celery.tasks import (  # noqa: E402
    analyze_task,
    design_task,
    discover_task,
    execute_task,
    generate_scripts_task,
    report_task,
)

PAYLOAD = {
    "pipelineRunId": "00000000-0000-0000-0000-000000000001",
    "applicationId": "00000000-0000-0000-0000-000000000002",
    "pluginId": "ui",
    "mode": "ui",
}

AGENT_TASKS = [
    ("discover", discover_task, "discovery", "pages"),
    ("design", design_task, "test-design", "test_cases"),
    ("generate_scripts", generate_scripts_task, "script-generation", "code"),
    ("analyze", analyze_task, "intelligence", "coverage"),
]

STUB_TASKS = [
    ("execute", execute_task),
    ("report", report_task),
]


def main() -> int:
    for label, task, agent_id, output_key in AGENT_TASKS:
        result = task.run(PAYLOAD)
        if not result.get("ok"):
            print(f"FAIL {label}: not ok", file=sys.stderr)
            return 1
        if result.get("agentId") != agent_id:
            print(f"FAIL {label}: agentId={result.get('agentId')}", file=sys.stderr)
            return 1
        if output_key not in result.get("output", {}):
            print(f"FAIL {label}: missing output.{output_key}", file=sys.stderr)
            return 1
        print(f"OK {label}: agent={agent_id} output keys={list(result['output'].keys())}")

    for label, task in STUB_TASKS:
        result = task.run(PAYLOAD)
        if not result.get("ok") or not result.get("stub"):
            print(f"FAIL {label}: expected stub result", file=sys.stderr)
            return 1
        print(f"OK {label}: stub task")

    print("verify:worker-agents OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
