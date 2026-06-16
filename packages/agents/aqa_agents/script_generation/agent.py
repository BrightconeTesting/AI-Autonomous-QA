"""ScriptGenerationAgent implementation."""

from aqa_shared.types.agent import AgentContext, AgentResult

from aqa_agents.base import invoke_stub_graph, log_agent_run, stub_result
from aqa_agents.script_generation.graph import build_graph
from aqa_agents.script_generation.models import ScriptGenerationInput, ScriptGenerationOutput


class ScriptGenerationAgent:
    id = "script-generation"

    def run(self, input: ScriptGenerationInput, ctx: AgentContext) -> AgentResult:
        log_agent_run(self.id, ctx)
        graph = build_graph()
        final = invoke_stub_graph(graph, {})
        output = ScriptGenerationOutput.model_validate(final["output"])
        return stub_result(output)
