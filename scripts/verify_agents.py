#!/usr/bin/env python3
"""Verify all five core agent stubs (Day 8)."""

import logging
import sys

from aqa_agents import (
    ALL_AGENTS,
    DiscoveryAgent,
    DiscoveryInput,
    HealingAgent,
    HealingInput,
    IntelligenceAgent,
    IntelligenceInput,
    ScriptGenerationAgent,
    ScriptGenerationInput,
    TestDesignAgent,
    TestDesignInput,
)
from aqa_shared.types.agent import AgentContext

logging.basicConfig(level=logging.INFO)

CTX = AgentContext(
    pipelineRunId="00000000-0000-0000-0000-000000000001",
    applicationId="00000000-0000-0000-0000-000000000002",
    pluginId="ui",
    mode="ui",
    tokenBudgetRemaining=8000,
)

HEALING_PAYLOAD = {"code": "// broken", "reason": "locator not found"}


def main() -> int:
    checks: list[tuple[str, object]] = [
        ("discovery", DiscoveryAgent().run(DiscoveryInput(), CTX).output),
        ("test-design", TestDesignAgent().run(TestDesignInput(), CTX).output),
        ("script-generation", ScriptGenerationAgent().run(ScriptGenerationInput(), CTX).output),
        ("intelligence", IntelligenceAgent().run(IntelligenceInput(), CTX).output),
        (
            "healing",
            HealingAgent().run(HealingInput(payload=HEALING_PAYLOAD), CTX).output,
        ),
    ]

    print("verify:agents OK")
    for agent_id, output in checks:
        print(f"  {agent_id}: {output}")

    healing_out = checks[-1][1]
    if getattr(healing_out, "payload", None) != HEALING_PAYLOAD:
        print("healing pass-through FAILED", file=sys.stderr)
        return 1

    if len(ALL_AGENTS) != 5:
        print(f"expected 5 agents, got {len(ALL_AGENTS)}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
