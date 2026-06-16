"""LangGraph stub for DiscoveryAgent — expandable in Phase 1+."""

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from aqa_agents.discovery.models import DiscoveryOutput


class DiscoveryState(TypedDict):
    output: dict[str, Any]


def _stub_node(_state: DiscoveryState) -> DiscoveryState:
    return {"output": DiscoveryOutput().model_dump()}


def build_graph():
    graph = StateGraph(DiscoveryState)
    graph.add_node("stub", _stub_node)
    graph.add_edge(START, "stub")
    graph.add_edge("stub", END)
    return graph.compile()
