#!/usr/bin/env python3
"""Verify flow confidence attachment (M0)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/agents"))

from aqa_agents.discovery.flow_structure import _annotate_rule_flows, validate_llm_flows  # noqa: E402


def main() -> int:
    print("verify:flow-confidence")
    pages = [{"page_id": "p1", "url": "https://example.com/app/dashboard"}]
    elements = []
    rule_flows = [
        {
            "name": "Dashboard flow",
            "steps": [
                {
                    "action": "navigate",
                    "page_id": "p1",
                    "url": "https://example.com/app/dashboard",
                }
            ],
            "source": "crawler",
        }
    ]
    annotated = _annotate_rule_flows(rule_flows)
    assert annotated[0]["confidence"] == 1.0
    assert "rule:deterministic" in annotated[0]["confidence_factors"]

    accepted = validate_llm_flows(
        [
            {
                "name": "LLM Dashboard",
                "steps": rule_flows[0]["steps"],
            }
        ],
        rule_flows=rule_flows,
        pages=pages,
        elements=elements,
    )
    assert accepted[0]["confidence"] == 0.9
    assert accepted[0]["review_required"] is False

    print("verify:flow-confidence OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
