#!/usr/bin/env python3
"""Run full discovery MVP verify gates (M0–M3)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CHECKS = [
    "verify:discovery-m0",
    "verify:discovery-m1",
    "verify:discovery-m2",
    "verify:discovery-summary",
]


def main() -> int:
    print("verify:discovery-mvp")
    for script in CHECKS:
        result = subprocess.run(["pnpm", script], cwd=ROOT, check=False)
        if result.returncode != 0:
            print(f"FAIL {script} exit={result.returncode}", file=sys.stderr)
            return 1
    print("verify:discovery-mvp OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
