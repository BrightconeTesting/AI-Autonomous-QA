"""HealingAgent implementation — returns input unchanged."""

from aqa_shared.types.agent import AgentContext, AgentResult

from aqa_agents.base import invoke_stub_graph, log_agent_run, stub_result
from aqa_agents.healing.graph import build_graph
from aqa_agents.healing.models import HealingInput, HealingOutput


class HealingAgent:
    id = "healing"

    def run(self, input: HealingInput, ctx: AgentContext) -> AgentResult:
        log_agent_run(self.id, ctx)
        graph = build_graph()
        final = invoke_stub_graph(graph, {"input": input.model_dump(), "output": {}})
        output = HealingOutput.model_validate(final["output"])
        return stub_result(output)
