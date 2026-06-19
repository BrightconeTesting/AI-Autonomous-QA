"""TestDesignAgent implementation."""

from __future__ import annotations

import logging
import uuid

from aqa_shared.db.session import get_session_factory
from aqa_shared.types.agent import AgentContext, AgentResult

from aqa_agents.base import log_agent_run, stub_result
from aqa_agents.discovery.appmap import load_appmap_for_application
from aqa_agents.test_design.models import TestDesignInput, TestDesignOutput
from aqa_agents.test_design.templates import generate_test_cases

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
            return stub_result(TestDesignOutput())

        test_cases = generate_test_cases(
            appmap,
            max_tests=input.max_tests,
            priorities=input.priorities,
        )
        logger.info(
            "TestDesignAgent generated rule-based test cases",
            extra={
                "applicationId": ctx.application_id,
                "pipelineRunId": ctx.pipeline_run_id,
                "testCaseCount": len(test_cases),
                "schemaVersion": appmap.get("schema_version"),
            },
        )
        return stub_result(TestDesignOutput(test_cases=test_cases))
