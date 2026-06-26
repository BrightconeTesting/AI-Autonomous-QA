#!/usr/bin/env python3
"""Run Phase H discovery verify gates."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CHECKS = [
    "verify:discovery-feedback",
    "verify:discovery-phase-e",
]


def main() -> int:
    print("verify:discovery-phase-h")
    for script in CHECKS:
        result = subprocess.run(["pnpm", script], cwd=ROOT, check=False)
        if result.returncode != 0:
            print(f"FAIL {script} exit={result.returncode}", file=sys.stderr)
            return 1
    print("verify:discovery-phase-h OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
