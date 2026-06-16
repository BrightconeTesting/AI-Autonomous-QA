"""LangGraph stub for ScriptGenerationAgent."""

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from aqa_agents.script_generation.models import ScriptGenerationOutput


class ScriptGenerationState(TypedDict):
    output: dict[str, Any]


def _stub_node(_state: ScriptGenerationState) -> ScriptGenerationState:
    return {"output": ScriptGenerationOutput().model_dump()}


def build_graph():
    graph = StateGraph(ScriptGenerationState)
    graph.add_node("stub", _stub_node)
    graph.add_edge(START, "stub")
    graph.add_edge("stub", END)
    return graph.compile()
