"""Unit tests for CIC Phase 3 modules."""

from __future__ import annotations

from aqa_discovery.cic.planner import plan_interactions
from aqa_discovery.interaction_safety import canned_fill_value, is_safe_to_interact
from aqa_discovery.types import ElementSnapshot


def test_planner_native_select_action_type() -> None:
    elements = [
        ElementSnapshot(
            tag_name="select",
            role="combobox",
            text_content="Active",
            attributes={"name": "status"},
            is_visible=True,
        ),
    ]
    actions = plan_interactions(elements, page_url="https://example.com", rich_interactions=True)
    assert len(actions) == 1
    assert actions[0].action_type == "select"


def test_planner_combobox_click_action_type() -> None:
    elements = [
        ElementSnapshot(
            tag_name="button",
            role="combobox",
            text_content="Pick role",
            attributes={"aria-haspopup": "listbox", "aria-expanded": "false"},
            is_visible=True,
        ),
    ]
    actions = plan_interactions(elements, page_url="https://example.com", rich_interactions=True)
    assert len(actions) == 1
    assert actions[0].action_type == "click"


def test_planner_hover_menu_action_type() -> None:
    elements = [
        ElementSnapshot(
            tag_name="button",
            role="button",
            text_content="Reports",
            attributes={"aria-haspopup": "menu"},
            is_visible=True,
        ),
    ]
    actions = plan_interactions(elements, page_url="https://example.com", rich_interactions=True)
    assert len(actions) == 1
    assert actions[0].action_type == "hover"


def test_planner_fill_when_safe_form_fill_enabled() -> None:
    elements = [
        ElementSnapshot(
            tag_name="input",
            role="textbox",
            attributes={"type": "text", "placeholder": "Company name"},
            is_visible=True,
        ),
    ]
    actions = plan_interactions(
        elements,
        page_url="https://example.com",
        rich_interactions=True,
        safe_form_fill=True,
        in_page_only=False,
    )
    assert len(actions) == 1
    assert actions[0].action_type == "fill"
    assert actions[0].value == "Test value"


def test_safety_blocks_password_fill() -> None:
    element = ElementSnapshot(
        tag_name="input",
        role="textbox",
        attributes={"type": "password"},
        is_visible=True,
    )
    safe, reason = is_safe_to_interact(element, page_url="https://example.com", allow_form_fill=True)
    assert safe is False
    assert reason == "password_field"


def test_canned_fill_email() -> None:
    assert canned_fill_value({"type": "email"}) == "test@example.com"
