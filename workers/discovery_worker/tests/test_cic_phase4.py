"""Unit tests for CIC Phase 4 modules."""

from __future__ import annotations

from aqa_agents.discovery.flows import (
    _enumerate_transition_paths,
    _interaction_step,
    build_flows_from_states,
)
from aqa_discovery.cic.planner import plan_interactions
from aqa_discovery.types import ElementSnapshot


def test_interaction_step_preserves_action_type() -> None:
    step = _interaction_step(
        {"action_type": "select", "semantic_selector": "sel", "text_content": "Status"},
        {"state_key": "s_child"},
    )
    assert step["action"] == "select"
    assert step["state_key"] == "s_child"


def test_transition_graph_paths() -> None:
    states = [
        {"state_id": "s0", "page_id": "p1", "state_key": "root", "interaction_depth": 0},
        {"state_id": "s1", "page_id": "p1", "state_key": "child_a", "interaction_depth": 1},
        {"state_id": "s2", "page_id": "p1", "state_key": "child_b", "interaction_depth": 1},
    ]
    transitions = [
        {
            "from_state_id": "s0",
            "to_state_id": "s1",
            "action": {"action_type": "click", "text_content": "Tab A"},
        },
        {
            "from_state_id": "s0",
            "to_state_id": "s2",
            "action": {"action_type": "hover", "text_content": "Menu"},
        },
    ]
    paths = _enumerate_transition_paths("s0", transitions, {s["state_id"]: s for s in states}, max_paths=5)
    assert len(paths) == 2
    assert paths[0][0]["action"] == "click"
    assert paths[1][0]["action"] == "hover"


def test_graph_flow_builder() -> None:
    pages = [{"page_id": "p1", "url": "https://example.com/app", "title": "App"}]
    states = [
        {"state_id": "s0", "page_id": "p1", "state_key": "root", "interaction_depth": 0, "parent_state_key": None},
        {"state_id": "s1", "page_id": "p1", "state_key": "child", "interaction_depth": 1, "parent_state_key": "root"},
    ]
    transitions = [
        {
            "from_state_id": "s0",
            "to_state_id": "s1",
            "action": {"action_type": "select", "text_content": "Open"},
        },
    ]
    flows = build_flows_from_states(pages, states, transitions)
    assert len(flows) == 1
    assert flows[0]["steps"][0]["action"] == "navigate"
    assert flows[0]["steps"][1]["action"] == "select"


def test_planner_table_pagination() -> None:
    elements = [
        ElementSnapshot(
            tag_name="button",
            role="button",
            text_content="Next",
            attributes={"aria-label": "Next page"},
            is_visible=True,
        ),
    ]
    actions = plan_interactions(
        elements,
        page_url="https://example.com",
        rich_interactions=True,
        enable_tables=True,
        in_page_only=False,
    )
    assert len(actions) == 1
    assert actions[0].action_type == "click"


def test_planner_date_picker() -> None:
    elements = [
        ElementSnapshot(
            tag_name="input",
            role="textbox",
            attributes={"type": "date", "id": "start"},
            is_visible=True,
        ),
    ]
    actions = plan_interactions(
        elements,
        page_url="https://example.com",
        rich_interactions=True,
        enable_date_pickers=True,
        in_page_only=True,
    )
    assert len(actions) == 1
    assert actions[0].action_type == "click"
