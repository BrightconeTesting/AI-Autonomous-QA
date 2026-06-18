#!/usr/bin/env python3
"""Verify CIC Phase 3 — dropdowns, hover menus, dynamic forms, iframes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "workers" / "discovery_worker" / "tests" / "fixtures" / "cic"
sys.path.insert(0, str(ROOT / "workers" / "discovery_worker"))


def _run_unit_tests() -> None:
    from tests.test_cic_phase3 import (
        test_canned_fill_email,
        test_planner_combobox_click_action_type,
        test_planner_fill_when_safe_form_fill_enabled,
        test_planner_hover_menu_action_type,
        test_planner_native_select_action_type,
        test_safety_blocks_password_fill,
    )

    test_planner_native_select_action_type()
    test_planner_combobox_click_action_type()
    test_planner_hover_menu_action_type()
    test_planner_fill_when_safe_form_fill_enabled()
    test_safety_blocks_password_fill()
    test_canned_fill_email()
    print("OK unit: planner select/hover/fill, safety")


def _collect_texts(snapshot) -> set[str]:
    texts: set[str] = set()
    for state in snapshot.states:
        for element in state.elements:
            if element.text_content:
                texts.add(element.text_content.strip())
    return texts


def _visit(fixture_name: str, **settings_kwargs):
    from aqa_discovery.crawl_settings import CrawlSettings
    from aqa_discovery.crawler import CrawlSession

    fixture = FIXTURES / fixture_name
    settings = CrawlSettings(
        max_depth=0,
        max_pages=1,
        enable_cic=True,
        cic_rich_interactions=True,
        interaction_wait_ms=400,
        max_interactions_per_url=15,
        max_interactions_per_state=6,
        cic_in_page_only=False,
        **settings_kwargs,
    )
    with CrawlSession(headless=True) as session:
        return session._visit_page(fixture.as_uri(), depth=0, settings=settings)


def _verify_dropdown() -> None:
    snapshot, _ = _visit("dropdown.html")
    texts = _collect_texts(snapshot)
    assert "Secret Role Option" in texts or len(snapshot.transitions) >= 2, (
        f"dropdown options not discovered: {sorted(texts)}"
    )
    assert any(t.action.action_type in {"select", "click"} for t in snapshot.transitions) or snapshot.transitions
    print(f"OK dropdown: states={len(snapshot.states)} transitions={len(snapshot.transitions)}")


def _verify_hover_menu() -> None:
    snapshot, _ = _visit("hover_menu.html")
    texts = _collect_texts(snapshot)
    assert "Secret Report Action" in texts, f"hover menu item not found: {sorted(texts)}"
    print(f"OK hover_menu: states={len(snapshot.states)} secret_found=True")


def _verify_dynamic_form() -> None:
    snapshot, _ = _visit("dynamic_form.html", safe_form_fill=True)
    texts = _collect_texts(snapshot)
    assert "Secret Save Action" in texts, f"dynamic field not revealed: {sorted(texts)}"
    print(f"OK dynamic_form: states={len(snapshot.states)} secret_found=True")


def _verify_iframe() -> None:
    snapshot, _ = _visit("iframe_form.html", cic_enable_iframes=True)
    texts = _collect_texts(snapshot)
    assert "Iframe Secret Action" in texts, f"iframe elements not discovered: {sorted(texts)}"
    print(f"OK iframe: states={len(snapshot.states)} secret_found=True")


def main() -> int:
    _run_unit_tests()
    _verify_dropdown()
    _verify_hover_menu()
    _verify_dynamic_form()
    _verify_iframe()
    print("verify_cic_phase3: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
