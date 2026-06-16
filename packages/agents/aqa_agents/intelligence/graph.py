"""LangGraph stub for IntelligenceAgent (no LLM in MVP coverage mode)."""

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from aqa_agents.intelligence.models import IntelligenceOutput


class IntelligenceState(TypedDict):
    output: dict[str, Any]


def _stub_node(_state: IntelligenceState) -> IntelligenceState:
    return {"output": IntelligenceOutput().model_dump()}


def build_graph():
    graph = StateGraph(IntelligenceState)
    graph.add_node("stub", _stub_node)
    graph.add_edge(START, "stub")
    graph.add_edge("stub", END)
    return graph.compile()
