"""TestDesignAgent implementation."""

from aqa_shared.types.agent import AgentContext, AgentResult

from aqa_agents.base import invoke_stub_graph, log_agent_run, stub_result
from aqa_agents.test_design.graph import build_graph
from aqa_agents.test_design.models import TestDesignInput, TestDesignOutput


class TestDesignAgent:
    id = "test-design"

    def run(self, input: TestDesignInput, ctx: AgentContext) -> AgentResult:
        log_agent_run(self.id, ctx)
        graph = build_graph()
        final = invoke_stub_graph(graph, {})
        output = TestDesignOutput.model_validate(final["output"])
        return stub_result(output)
