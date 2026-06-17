"""DiscoveryAgent implementation — rule-based flows + AppMap (Day 20)."""

from __future__ import annotations

import logging
import uuid

from aqa_shared.types.agent import AgentContext, AgentResult

from aqa_agents.base import log_agent_run, stub_result
from aqa_agents.discovery.appmap import build_and_persist_appmap
from aqa_agents.discovery.models import DiscoveryInput, DiscoveryOutput

logger = logging.getLogger(__name__)


class DiscoveryAgent:
    id = "discovery"

    def run(self, input: DiscoveryInput, ctx: AgentContext) -> AgentResult:
        log_agent_run(self.id, ctx)
        try:
            app_id = uuid.UUID(ctx.application_id)
            pipeline_run_id = uuid.UUID(ctx.pipeline_run_id)
            result = build_and_persist_appmap(
                application_id=app_id,
                pipeline_run_id=pipeline_run_id,
            )
        except (ValueError, RuntimeError) as exc:
            logger.warning(
                "DiscoveryAgent AppMap skipped",
                extra={
                    "applicationId": ctx.application_id,
                    "pipelineRunId": ctx.pipeline_run_id,
                    "error": str(exc),
                },
            )
            return stub_result(DiscoveryOutput())

        output = DiscoveryOutput(
            pages=result.pages,
            flows=result.flows,
            stats={
                "page_count": result.page_count,
                "element_count": result.element_count,
                "flow_count": result.flow_count,
                "appmap_hash": result.appmap_hash,
                "appmap_path": result.appmap_path,
            },
        )
        return stub_result(output)
