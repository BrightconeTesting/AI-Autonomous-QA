#!/usr/bin/env python3
"""Run M0 discovery foundation verify gates."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CHECKS = [
    "verify:llm-budget",
    "verify:flow-confidence",
    "verify:discovery-architecture",
    "verify:appmap-approval",
    "verify:discovery-llm",
]


def main() -> int:
    print("verify:discovery-m0")
    for script in CHECKS:
        result = subprocess.run(["pnpm", script], cwd=ROOT, check=False)
        if result.returncode != 0:
            print(f"FAIL {script} exit={result.returncode}", file=sys.stderr)
            return 1
    print("verify:discovery-m0 OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
