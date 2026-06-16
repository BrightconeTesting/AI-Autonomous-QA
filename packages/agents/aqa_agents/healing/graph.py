"""LangGraph stub for HealingAgent — pass-through until Phase 3 repair logic."""

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph


class HealingState(TypedDict):
    input: dict[str, Any]
    output: dict[str, Any]


def _pass_through_node(state: HealingState) -> HealingState:
    return {"output": dict(state["input"])}


def build_graph():
    graph = StateGraph(HealingState)
    graph.add_node("pass_through", _pass_through_node)
    graph.add_edge(START, "pass_through")
    graph.add_edge("pass_through", END)
    return graph.compile()
