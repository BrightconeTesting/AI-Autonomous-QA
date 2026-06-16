"""LangGraph stub for TestDesignAgent."""

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from aqa_agents.test_design.models import TestDesignOutput


class TestDesignState(TypedDict):
    output: dict[str, Any]


def _stub_node(_state: TestDesignState) -> TestDesignState:
    return {"output": TestDesignOutput().model_dump()}


def build_graph():
    graph = StateGraph(TestDesignState)
    graph.add_node("stub", _stub_node)
    graph.add_edge(START, "stub")
    graph.add_edge("stub", END)
    return graph.compile()
