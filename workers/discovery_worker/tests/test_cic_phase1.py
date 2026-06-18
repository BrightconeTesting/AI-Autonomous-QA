"""Unit tests for CIC Phase 1 modules."""

from __future__ import annotations

from aqa_discovery.cic.fingerprint import compute_state_fingerprint, state_key_from_fingerprint
from aqa_discovery.cic.planner import plan_interactions
from aqa_discovery.crawl_settings import CrawlSettings
from aqa_discovery.interaction_safety import is_safe_to_interact
from aqa_discovery.types import ElementSnapshot


def test_fingerprint_stable_for_same_elements() -> None:
    elements = [
        ElementSnapshot(tag_name="button", role="tab", text_content="Overview", is_visible=True),
        ElementSnapshot(tag_name="button", role="tab", text_content="Details", is_visible=True),
    ]
    fp1 = compute_state_fingerprint(url="https://example.com", title="Test", elements=elements)
    fp2 = compute_state_fingerprint(url="https://example.com", title="Test", elements=elements)
    assert fp1 == fp2
    assert state_key_from_fingerprint(fp1).startswith("s_")


def test_fingerprint_differs_when_elements_change() -> None:
    base = [ElementSnapshot(tag_name="button", role="tab", text_content="Overview", is_visible=True)]
    expanded = base + [
        ElementSnapshot(tag_name="button", role="button", text_content="Secret Action", is_visible=True)
    ]
    fp_base = compute_state_fingerprint(url="https://example.com", title="Test", elements=base)
    fp_expanded = compute_state_fingerprint(url="https://example.com", title="Test", elements=expanded)
    assert fp_base != fp_expanded


def test_safety_blocks_logout() -> None:
    element = ElementSnapshot(tag_name="button", role="button", text_content="Sign out", is_visible=True)
    safe, reason = is_safe_to_interact(element, page_url="https://example.com")
    assert safe is False
    assert reason == "dangerous_text"


def test_safety_blocks_file_input() -> None:
    element = ElementSnapshot(
        tag_name="input",
        role="textbox",
        attributes={"type": "file"},
        is_visible=True,
    )
    safe, reason = is_safe_to_interact(element, page_url="https://example.com")
    assert safe is False


def test_planner_prioritizes_tabs() -> None:
    elements = [
        ElementSnapshot(tag_name="button", role="button", text_content="Save", is_visible=True),
        ElementSnapshot(tag_name="button", role="tab", text_content="Details", is_visible=True),
    ]
    actions = plan_interactions(elements, page_url="https://example.com")
    assert len(actions) == 1
    assert actions[0].role == "tab"


def test_planner_skips_navigation_links() -> None:
    elements = [
        ElementSnapshot(
            tag_name="a",
            role="link",
            text_content="Dashboard",
            attributes={"href": "/dashboard"},
            is_visible=True,
        ),
        ElementSnapshot(tag_name="button", role="tab", text_content="Settings", is_visible=True),
    ]
    actions = plan_interactions(elements, page_url="https://example.com")
    assert len(actions) == 1
    assert actions[0].role == "tab"


def test_planner_full_mode_includes_buttons() -> None:
    elements = [
        ElementSnapshot(tag_name="button", role="button", text_content="Save", is_visible=True),
        ElementSnapshot(tag_name="button", role="tab", text_content="Details", is_visible=True),
    ]
    actions = plan_interactions(elements, page_url="https://example.com", in_page_only=False)
    assert len(actions) == 2
    assert actions[0].role == "tab"


def test_fast_cic_defaults_from_crawl_config() -> None:
    settings = CrawlSettings.from_crawl_config(
        "https://example.com",
        {"enable_cic": True},
    )
    assert settings.cic_mode == "fast"
    assert settings.interaction_wait_strategy == "fixed_ms"
    assert settings.interaction_wait_ms == 350
    assert settings.max_interactions_per_url == 12
    assert settings.cic_in_page_only is True
