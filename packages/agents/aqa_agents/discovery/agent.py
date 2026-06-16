"""DiscoveryAgent implementation."""

from aqa_shared.types.agent import AgentContext, AgentResult

from aqa_agents.base import invoke_stub_graph, log_agent_run, stub_result
from aqa_agents.discovery.graph import build_graph
from aqa_agents.discovery.models import DiscoveryInput, DiscoveryOutput


class DiscoveryAgent:
    id = "discovery"

    def run(self, input: DiscoveryInput, ctx: AgentContext) -> AgentResult:
        log_agent_run(self.id, ctx)
        graph = build_graph()
        final = invoke_stub_graph(graph, {})
        output = DiscoveryOutput.model_validate(final["output"])
        return stub_result(output)
