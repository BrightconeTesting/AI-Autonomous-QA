#!/usr/bin/env python3
"""Verify DiscoveryWorker vs DiscoveryAgent boundary (M0)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER_ROOT = ROOT / "workers/discovery_worker/aqa_discovery"
AGENT_ROOT = ROOT / "packages/agents/aqa_agents/discovery"


def _py_files(directory: Path) -> list[Path]:
    return [path for path in directory.rglob("*.py") if path.is_file()]


def main() -> int:
    print("verify:discovery-architecture")
    violations: list[str] = []

    for path in _py_files(WORKER_ROOT):
        text = path.read_text(encoding="utf-8")
        if re.search(r"^\s*(from|import)\s+openai\b", text, re.MULTILINE):
            violations.append(f"worker imports openai: {path.relative_to(ROOT)}")
        if "aqa_agents.discovery" in text:
            violations.append(f"worker imports DiscoveryAgent package: {path.relative_to(ROOT)}")

    for path in _py_files(AGENT_ROOT):
        text = path.read_text(encoding="utf-8")
        if re.search(r"^\s*(from|import)\s+playwright\b", text, re.MULTILINE):
            violations.append(f"agent imports playwright: {path.relative_to(ROOT)}")
        if re.search(r"^\s*(from|import)\s+aqa_discovery\b", text, re.MULTILINE):
            violations.append(f"agent imports discovery worker: {path.relative_to(ROOT)}")

    if violations:
        for item in violations:
            print(f"FAIL {item}", file=sys.stderr)
        return 1

    print("verify:discovery-architecture OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
