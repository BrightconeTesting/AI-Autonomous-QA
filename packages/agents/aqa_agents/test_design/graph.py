"""LangGraph pipeline for TestDesignAgent (Day 23)."""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from aqa_agents.test_design.gap_fill import gap_fill_test_cases
from aqa_agents.test_design.models import TestDesignOutput
from aqa_agents.test_design.templates import generate_test_cases
from aqa_agents.test_design.validate_merge import merge_test_cases, validate_and_filter_cases


class TestDesignState(TypedDict, total=False):
    appmap: dict[str, Any]
    max_tests: int
    priorities: list[str]
    use_llm: bool
    token_budget_remaining: int
    rule_cases: list[dict[str, Any]]
    llm_cases: list[dict[str, Any]]
    test_cases: list[dict[str, Any]]
    tokens_used: int
    cost_estimate: float
    validation_passed: bool
    rejection_reasons: list[str]
    llm_skip_reason: str | None


def _rule_templates_node(state: TestDesignState) -> TestDesignState:
    appmap = state.get("appmap") or {}
    rule_cases = generate_test_cases(
        appmap,
        max_tests=int(state.get("max_tests") or 50),
        priorities=list(state.get("priorities") or ["critical", "high"]),
    )
    return {"rule_cases": rule_cases}


def _gap_fill_node(state: TestDesignState) -> TestDesignState:
    llm_cases, tokens_used, cost_estimate, skip_reason = gap_fill_test_cases(
        state.get("appmap") or {},
        rule_cases=list(state.get("rule_cases") or []),
        max_tests=int(state.get("max_tests") or 50),
        priorities=list(state.get("priorities") or ["critical", "high"]),
        use_llm=bool(state.get("use_llm", True)),
        token_budget_remaining=int(state.get("token_budget_remaining") or 0),
    )
    return {
        "llm_cases": llm_cases,
        "tokens_used": int(state.get("tokens_used") or 0) + tokens_used,
        "cost_estimate": float(state.get("cost_estimate") or 0.0) + cost_estimate,
        "llm_skip_reason": skip_reason,
    }


def _merge_validate_node(state: TestDesignState) -> TestDesignState:
    merged = merge_test_cases(
        list(state.get("rule_cases") or []),
        list(state.get("llm_cases") or []),
    )
    accepted, rejections = validate_and_filter_cases(merged, state.get("appmap") or {})
    return {
        "test_cases": accepted,
        "validation_passed": True,
        "rejection_reasons": rejections,
    }


def build_graph():
    graph = StateGraph(TestDesignState)
    graph.add_node("rule_templates", _rule_templates_node)
    graph.add_node("gap_fill", _gap_fill_node)
    graph.add_node("merge_validate", _merge_validate_node)
    graph.add_edge(START, "rule_templates")
    graph.add_edge("rule_templates", "gap_fill")
    graph.add_edge("gap_fill", "merge_validate")
    graph.add_edge("merge_validate", END)
    return graph.compile()


def run_test_design_pipeline(
    *,
    appmap: dict[str, Any],
    max_tests: int,
    priorities: list[str],
    use_llm: bool,
    token_budget_remaining: int,
) -> TestDesignOutput:
    graph = build_graph()
    final = graph.invoke(
        {
            "appmap": appmap,
            "max_tests": max_tests,
            "priorities": priorities,
            "use_llm": use_llm,
            "token_budget_remaining": token_budget_remaining,
            "tokens_used": 0,
            "cost_estimate": 0.0,
        }
    )
    return TestDesignOutput(test_cases=list(final.get("test_cases") or []))
