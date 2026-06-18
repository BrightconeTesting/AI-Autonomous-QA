"""Unit tests for CIC Phase 2 modules."""

from __future__ import annotations

from aqa_agents.discovery.flows import build_flows_from_states
from aqa_discovery.cic.planner import plan_interactions
from aqa_discovery.cic.url_compare import is_at_baseline, is_url_discovery, normalize_discovery_url
from aqa_discovery.types import ElementSnapshot


def test_url_compare_hash_routes_differ() -> None:
    base = "https://example.com/app#/home"
    other = "https://example.com/app#/settings"
    assert normalize_discovery_url(base) != normalize_discovery_url(other)
    assert is_at_baseline(base, base)
    assert not is_at_baseline(other, base)
    assert is_url_discovery(base, other, base)


def test_planner_includes_hash_route_links() -> None:
    elements = [
        ElementSnapshot(
            tag_name="a",
            role="link",
            text_content="Settings",
            attributes={"href": "#/settings"},
            is_visible=True,
        ),
        ElementSnapshot(tag_name="button", role="tab", text_content="Overview", is_visible=True),
    ]
    actions = plan_interactions(elements, page_url="https://example.com/app")
    assert len(actions) == 2
    assert actions[0].role == "tab"


def test_planner_includes_modal_trigger() -> None:
    elements = [
        ElementSnapshot(
            tag_name="button",
            role="button",
            text_content="Open Info",
            attributes={"aria-haspopup": "dialog", "aria-controls": "info-modal"},
            is_visible=True,
        ),
    ]
    actions = plan_interactions(elements, page_url="https://example.com")
    assert len(actions) == 1
    assert actions[0].text_content == "Open Info"


def test_planner_includes_wizard_buttons() -> None:
    elements = [
        ElementSnapshot(
            tag_name="button",
            role="button",
            text_content="Next",
            attributes={"type": "button"},
            is_visible=True,
        ),
    ]
    actions = plan_interactions(elements, page_url="https://example.com")
    assert len(actions) == 1
    assert actions[0].text_content == "Next"


def test_discovery_flow_navigate_click_navigate() -> None:
    pages = [
        {"page_id": "p1", "url": "https://example.com/app", "title": "App"},
        {"page_id": "p2", "url": "https://example.com/app#/settings", "title": "Settings"},
    ]
    discoveries = [
        {
            "discovered_via": "interaction",
            "source_page_id": "p1",
            "source_state_key": "s_base",
            "url": "https://example.com/app#/settings",
            "trigger_action": {
                "semantic_selector": "getByRole('link', { name: 'Settings' })",
                "text_content": "Settings",
                "role": "link",
            },
        }
    ]
    flows = build_flows_from_states(pages, [], [], discoveries=discoveries)
    assert len(flows) == 1
    steps = flows[0]["steps"]
    assert [step["action"] for step in steps] == ["navigate", "click", "navigate"]
    assert steps[0]["url"] == "https://example.com/app"
    assert steps[2]["url"] == "https://example.com/app#/settings"
    assert steps[2]["page_id"] == "p2"
