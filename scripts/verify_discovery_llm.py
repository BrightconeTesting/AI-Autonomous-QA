#!/usr/bin/env python3
"""Verify DiscoveryAgent LLM flow structuring — grounding + fallback."""

from __future__ import annotations

import os
import sys
import uuid
from unittest.mock import patch

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from aqa_agents.discovery.agent import DiscoveryAgent  # noqa: E402
from aqa_agents.discovery.flow_structure import (  # noqa: E402
    structure_flows_with_llm,
    validate_llm_flows,
)
from aqa_agents.discovery.flows import build_flows_from_pages  # noqa: E402
from aqa_agents.discovery.models import DiscoveryInput  # noqa: E402
from aqa_shared.types.agent import AgentContext  # noqa: E402

CTX = AgentContext(
    pipelineRunId=str(uuid.uuid4()),
    applicationId=str(uuid.uuid4()),
    pluginId="ui",
    mode="ui",
    tokenBudgetRemaining=8000,
)

PAGES = [
    {"page_id": "p1", "url": "https://example.com/app/home", "title": "Home"},
    {"page_id": "p2", "url": "https://example.com/app/settings", "title": "Settings"},
]
ELEMENTS = [
    {
        "page_id": "p2",
        "semantic_selector": "getByRole('tab', { name: 'Profile' })",
        "role": "tab",
        "text_content": "Profile",
    }
]


def _rule_flows() -> list[dict]:
    return build_flows_from_pages(PAGES)


def _assert_grounding_rejects_hallucinated_steps() -> None:
    rule = _rule_flows()
    bad = [
        {
            "name": "Bad flow",
            "description": "invalid",
            "steps": [{"action": "click", "semantic_selector": "getByRole('button', { name: 'Nope' })"}],
        }
    ]
    accepted = validate_llm_flows(bad, rule_flows=rule, pages=PAGES, elements=ELEMENTS)
    if accepted:
        raise AssertionError("expected hallucinated flow to be rejected")
    print("OK validate_llm_flows rejects ungrounded steps")


def _assert_rule_only_without_key() -> None:
    rule = _rule_flows()
    with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
        flows, tokens, cost, reason = structure_flows_with_llm(
            pages=PAGES,
            elements=ELEMENTS,
            rule_flows=rule,
            use_llm=True,
            token_budget_remaining=8000,
        )
    if tokens != 0:
        raise AssertionError(f"expected 0 tokens without key, got {tokens}")
    if len(flows) != len(rule):
        raise AssertionError("expected same number of rule flows without API key")
    for returned, original in zip(flows, rule, strict=True):
        if returned.get("name") != original.get("name"):
            raise AssertionError("expected rule flow names unchanged without API key")
        if returned.get("confidence") != 1.0:
            raise AssertionError("expected rule flow confidence on fallback")
    if reason != "OPENAI_API_KEY unset":
        raise AssertionError(f"unexpected skip reason: {reason}")
    print(f"OK LLM skipped without OPENAI_API_KEY ({len(flows)} rule flows)")


def _assert_mocked_llm_enhancement() -> None:
    import json

    rule = _rule_flows()
    enhanced = [
        {
            "name": "Home dashboard — primary navigation",
            "description": "Open the home dashboard landing page.",
            "module": "home",
            "steps": rule[0]["steps"],
        }
    ]
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
        with patch("openai.OpenAI") as mock_client:
            mock_client.return_value.chat.completions.create.return_value = type(
                "Resp",
                (),
                {
                    "choices": [
                        type(
                            "Choice",
                            (),
                            {
                                "message": type(
                                    "Msg",
                                    (),
                                    {"content": json.dumps({"flows": enhanced})},
                                )()
                            },
                        )()
                    ],
                    "usage": type(
                        "Usage", (), {"prompt_tokens": 100, "completion_tokens": 50}
                    )(),
                },
            )()
            flows, tokens, cost, reason = structure_flows_with_llm(
                pages=PAGES,
                elements=ELEMENTS,
                rule_flows=rule,
                use_llm=True,
                token_budget_remaining=8000,
            )

    if not flows or flows[0]["name"] != "Home dashboard — primary navigation":
        raise AssertionError(f"expected enhanced flow name, got {flows}")
    if flows[0].get("confidence", 0) < 0.8:
        raise AssertionError("expected LLM flow confidence metadata")
    if tokens != 150:
        raise AssertionError(f"expected token tracking, got {tokens}")
    if reason is not None:
        raise AssertionError(f"expected no skip reason, got {reason}")
    print("OK mocked LLM enhances flow names with grounded steps")


def _assert_agent_integration() -> None:
    agent = DiscoveryAgent()
    with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
        with patch("aqa_agents.discovery.agent.build_and_persist_appmap") as mock_build:
            from aqa_agents.discovery.appmap import AppMapBuildResult

            mock_build.return_value = AppMapBuildResult(
                page_count=2,
                element_count=1,
                flow_count=2,
                appmap_path="/tmp/appmap.json",
                appmap_hash="abc",
                flows=_rule_flows(),
                pages=PAGES,
                elements=ELEMENTS,
                tokens_used=0,
                llm_skip_reason="OPENAI_API_KEY unset",
            )
            result = agent.run(DiscoveryInput(use_llm=True), CTX)
    if result.tokens_used != 0:
        raise AssertionError("expected agent to surface token count")
    print("OK DiscoveryAgent returns AgentResult with LLM metadata")


def main() -> int:
    print("verify:discovery-llm")
    _assert_grounding_rejects_hallucinated_steps()
    _assert_rule_only_without_key()
    _assert_mocked_llm_enhancement()
    _assert_agent_integration()
    print("verify:discovery-llm OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
