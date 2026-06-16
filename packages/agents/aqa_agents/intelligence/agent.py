"""IntelligenceAgent implementation."""

from aqa_shared.types.agent import AgentContext, AgentResult

from aqa_agents.base import invoke_stub_graph, log_agent_run, stub_result
from aqa_agents.intelligence.graph import build_graph
from aqa_agents.intelligence.models import IntelligenceInput, IntelligenceOutput


class IntelligenceAgent:
    id = "intelligence"

    def run(self, input: IntelligenceInput, ctx: AgentContext) -> AgentResult:
        log_agent_run(self.id, ctx)
        graph = build_graph()
        final = invoke_stub_graph(graph, {})
        output = IntelligenceOutput.model_validate(final["output"])
        return stub_result(output)
