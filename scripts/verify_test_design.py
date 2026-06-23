#!/usr/bin/env python3
"""Verify TestDesignAgent Day 23 — validation gate, merge/dedupe, LLM fallback."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

from aqa_agents.test_design.agent import TestDesignAgent  # noqa: E402
from aqa_agents.test_design.models import TestDesignInput  # noqa: E402
from aqa_agents.test_design.validate_merge import (  # noqa: E402
    merge_test_cases,
    validate_and_filter_cases,
)
from aqa_shared.types.agent import AgentContext  # noqa: E402
from aqa_shared.validation import validate_test_case  # noqa: E402

CTX = AgentContext(
    pipelineRunId=str(uuid.uuid4()),
    applicationId=str(uuid.uuid4()),
    pluginId="ui",
    mode="functional",
    tokenBudgetRemaining=8000,
)

SAMPLE_APPMAP = {
    "schema_version": 2,
    "pages": [
        {
            "page_id": "p1",
            "url": "https://example.com/app/settings",
            "title": "Settings",
        }
    ],
    "elements": [
        {
            "page_id": "p1",
            "semantic_selector": "getByRole('tab', { name: 'Profile' })",
            "role": "tab",
            "text_content": "Profile",
        }
    ],
    "flows": [
        {
            "flow_id": "f1",
            "name": "Settings flow",
            "steps": [{"action": "navigate", "url": "https://example.com/app/settings"}],
        }
    ],
}


def _assert_schema_gate() -> None:
    bad = validate_test_case({"priority": "high", "steps": [{"action": "click"}]})
    if bad.valid:
        raise AssertionError("expected invalid test case to fail schema validation")
    print("OK validate_test_case rejects malformed cases")


def _assert_merge_priority() -> None:
    rule = [{"name": "Login smoke", "priority": "medium", "steps": [{"action": "navigate", "target": "https://example.com/app/settings"}]}]
    llm = [{"name": "login smoke", "priority": "critical", "steps": [{"action": "navigate", "target": "https://example.com/app/settings"}]}]
    merged = merge_test_cases(rule, llm)
    if len(merged) != 1:
        raise AssertionError(f"expected 1 merged case, got {len(merged)}")
    if merged[0]["priority"] != "critical":
        raise AssertionError("expected higher-priority duplicate to win")
    print("OK merge_test_cases dedupes by name and keeps higher priority")


def _assert_grounding_rejects_unknown_targets() -> None:
    cases = [
        {
            "name": "Bad selector case",
            "priority": "high",
            "steps": [{"action": "click", "target": "getByRole('button', { name: 'DoesNotExist' })"}],
        }
    ]
    accepted, rejections = validate_and_filter_cases(cases, SAMPLE_APPMAP)
    if accepted:
        raise AssertionError("expected unknown selector case to be rejected")
    if not rejections:
        raise AssertionError("expected rejection reason")
    print("OK validate_and_filter_cases rejects targets outside AppMap")


def _assert_rule_only_without_key() -> None:
    agent = TestDesignAgent()
    with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
        result = agent.run(
            TestDesignInput(app_map=SAMPLE_APPMAP, use_llm=True, max_tests=10),
            CTX,
        )
    if result.tokens_used != 0:
        raise AssertionError(f"expected 0 tokens without API key, got {result.tokens_used}")
    cases = result.output.test_cases
    if not cases:
        raise AssertionError("expected rule-based cases without LLM")
    print(f"OK LLM skipped without OPENAI_API_KEY ({len(cases)} rule cases)")


def _assert_llm_merge_with_mock() -> None:
    mock_llm_case = {
        "name": "Profile tab visibility",
        "priority": "high",
        "flow_id": "f1",
        "steps": [
            {"action": "navigate", "target": "https://example.com/app/settings"},
            {"action": "click", "target": "getByRole('tab', { name: 'Profile' })"},
            {"action": "assertVisible", "target": "getByRole('tab', { name: 'Profile' })"},
        ],
    }

    agent = TestDesignAgent()
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
        with patch(
            "aqa_agents.test_design.graph.gap_fill_test_cases",
            return_value=([mock_llm_case], 120, 0.0001, None),
        ):
            result = agent.run(
                TestDesignInput(app_map=SAMPLE_APPMAP, use_llm=True, max_tests=10),
                CTX,
            )

    names = {case["name"] for case in result.output.test_cases}
    if "Profile tab visibility" not in names:
        raise AssertionError(f"expected mocked LLM case in output, got {names}")
    if result.tokens_used != 120:
        raise AssertionError(f"expected token tracking from LLM mock, got {result.tokens_used}")
    print("OK mocked LLM cases merge, validate, and track tokens")


def main() -> int:
    print("verify:test-design")
    _assert_schema_gate()
    _assert_merge_priority()
    _assert_grounding_rejects_unknown_targets()
    _assert_rule_only_without_key()
    _assert_llm_merge_with_mock()
    print("verify:test-design OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
