#!/usr/bin/env python3
"""Verify per-stage LLM budget tracker (M0)."""

from __future__ import annotations

import sys

from aqa_shared.llm.budget import LlmBudgetTracker, parse_llm_budgets


def main() -> int:
    print("verify:llm-budget")
    budgets = parse_llm_budgets({"llm_budgets": {"flow_structure": 100, "total_cap": 150}})
    assert budgets["flow_structure"] == 100
    assert budgets["total_cap"] == 150

    tracker = LlmBudgetTracker(budgets)
    assert tracker.can_run_stage("flow_structure")
    assert tracker.remaining_for_stage("flow_structure") == 100

    tracker.record_usage("flow_structure", 60)
    assert tracker.remaining_for_stage("flow_structure") == 40
    assert tracker.remaining_for_stage("module_structure") == 90

    tracker.record_usage("flow_structure", 50)
    assert not tracker.can_run_stage("flow_structure")

    snapshot = tracker.usage_snapshot()
    assert snapshot["total_used"] == 110
    assert snapshot["stages"]["flow_structure"]["used"] == 110

    print("verify:llm-budget OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
