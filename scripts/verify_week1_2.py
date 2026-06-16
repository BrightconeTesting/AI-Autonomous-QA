#!/usr/bin/env python3
"""Week 1–2 exit gate: smoke checks + Celery E2E (spawns a temporary worker)."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "bin" / "python"
CELERY = ROOT / ".venv" / "bin" / "celery"


def _run(label: str, args: list[str], *, cwd: Path = ROOT) -> None:
    print(f"==> {label}")
    result = subprocess.run(args, cwd=cwd, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{label} failed (exit {result.returncode})")


def main() -> int:
    print("verify:week1-2")

    _run("smoke", [str(PYTHON), "scripts/verify_smoke.py"])

    worker = subprocess.Popen(
        [
            str(CELERY),
            "-A",
            "aqa_celery.app",
            "worker",
            "-Q",
            "discover,design,generate-scripts,execute,report,analyze",
            "--loglevel=warning",
            "--concurrency=1",
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(4)
        if worker.poll() is not None:
            raise RuntimeError("Celery worker failed to start")
        _run("e2e-celery", [str(PYTHON), "scripts/verify_e2e_celery.py"])
    finally:
        worker.terminate()
        try:
            worker.wait(timeout=10)
        except subprocess.TimeoutExpired:
            worker.kill()

    print("verify:week1-2 OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
