#!/usr/bin/env python3
"""Day 10 integration smoke test — runs verify scripts + API health/metrics."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

VERIFY_SCRIPTS = [
    "verify_shared.py",
    "verify_redis.py",
    "verify_db.py",
    "verify_agents.py",
    "verify_worker_agents.py",
    "verify_validation.py",
    "verify_metrics.py",
    "verify_celery_enqueue.py",
]

PYTHON = ROOT / ".venv" / "bin" / "python"


def _run_script(name: str) -> None:
    script = ROOT / "scripts" / name
    result = subprocess.run(
        [str(PYTHON), str(script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stdout, end="")
        print(result.stderr, end="", file=sys.stderr)
        raise RuntimeError(f"{name} failed with exit code {result.returncode}")
    print(result.stdout, end="")


def _check_api_routes() -> None:
    from aqa_api.main import app

    client = TestClient(app)

    health = client.get("/health")
    if health.status_code != 200:
        raise RuntimeError(f"/health returned {health.status_code}")
    body = health.json()
    if body.get("status") != "ok":
        raise RuntimeError(f"/health unhealthy: {body}")
    print("OK /health: status=ok db+redis")

    metrics = client.get("/metrics")
    if metrics.status_code != 200 or "aqa_queue_depth" not in metrics.text:
        raise RuntimeError("/metrics missing expected gauges")
    print("OK /metrics: Prometheus text")


def main() -> int:
    print("verify:smoke")
    for script in VERIFY_SCRIPTS:
        _run_script(script)

    _check_api_routes()
    print("verify:smoke OK")
    print("Note: run `pnpm verify:e2e-celery` with a Celery worker for full enqueue→result flow.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
