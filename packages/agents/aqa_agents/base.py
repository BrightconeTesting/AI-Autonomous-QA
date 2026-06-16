"""Shared agent utilities — logging and stub result helpers."""

from __future__ import annotations

import logging
from typing import Any, TypeVar

from aqa_shared.types.agent import AgentContext, AgentResult, CoreAgentId

logger = logging.getLogger(__name__)

TOutput = TypeVar("TOutput")


def log_agent_run(agent_id: CoreAgentId, ctx: AgentContext) -> None:
    logger.info(
        "Agent run started",
        extra={
            "agentId": agent_id,
            "mode": ctx.mode,
            "pipelineRunId": ctx.pipeline_run_id,
            "applicationId": ctx.application_id,
            "pluginId": ctx.plugin_id,
        },
    )


def stub_result(output: TOutput) -> AgentResult:
    return AgentResult(
        output=output,
        tokensUsed=0,
        costEstimate=0.0,
        validationPassed=True,
    )


def invoke_stub_graph(graph: Any, state: dict[str, Any]) -> dict[str, Any]:
    """Run a compiled LangGraph and return final state."""
    return graph.invoke(state)
