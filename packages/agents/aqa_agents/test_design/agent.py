"""TestDesignAgent implementation."""

from __future__ import annotations

import logging
import uuid

from aqa_shared.db.session import get_session_factory
from aqa_shared.types.agent import AgentContext, AgentResult

from aqa_agents.base import log_agent_run
from aqa_agents.discovery.appmap import load_appmap_for_application
from aqa_agents.test_design.graph import build_graph
from aqa_agents.test_design.models import TestDesignInput, TestDesignOutput

logger = logging.getLogger(__name__)


class TestDesignAgent:
    id = "test-design"

    def _load_app_map(self, input: TestDesignInput, ctx: AgentContext) -> dict | None:
        if input.app_map:
            return input.app_map
        if ctx.app_map:
            return ctx.app_map
        try:
            app_id = uuid.UUID(ctx.application_id)
        except ValueError:
            return None
        session = get_session_factory()()
        try:
            return load_appmap_for_application(session, app_id)
        except Exception as exc:
            logger.warning(
                "TestDesignAgent AppMap load failed",
                extra={"applicationId": ctx.application_id, "error": str(exc)},
            )
            return None
        finally:
            session.close()

    def run(self, input: TestDesignInput, ctx: AgentContext) -> AgentResult:
        log_agent_run(self.id, ctx)
        appmap = self._load_app_map(input, ctx)
        if not appmap:
            return AgentResult(
                output=TestDesignOutput(),
                tokensUsed=0,
                costEstimate=0.0,
                validationPassed=True,
            )

        graph = build_graph()
        final = graph.invoke(
            {
                "appmap": appmap,
                "max_tests": input.max_tests,
                "priorities": input.priorities,
                "use_llm": input.use_llm,
                "token_budget_remaining": ctx.token_budget_remaining,
                "tokens_used": 0,
                "cost_estimate": 0.0,
            }
        )

        test_cases = list(final.get("test_cases") or [])
        tokens_used = int(final.get("tokens_used") or 0)
        cost_estimate = float(final.get("cost_estimate") or 0.0)
        skip_reason = final.get("llm_skip_reason")
        rejections = list(final.get("rejection_reasons") or [])

        logger.info(
            "TestDesignAgent completed",
            extra={
                "applicationId": ctx.application_id,
                "pipelineRunId": ctx.pipeline_run_id,
                "testCaseCount": len(test_cases),
                "tokensUsed": tokens_used,
                "costEstimate": cost_estimate,
                "llmSkipReason": skip_reason,
                "rejectedCount": len(rejections),
                "schemaVersion": appmap.get("schema_version"),
            },
        )

        return AgentResult(
            output=TestDesignOutput(test_cases=test_cases),
            tokensUsed=tokens_used,
            costEstimate=cost_estimate,
            validationPassed=True,
        )
