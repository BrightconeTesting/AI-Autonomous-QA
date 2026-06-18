#!/usr/bin/env python3
"""Verify CIC Phase 2 — modals, hash SPA, wizard, discovery flows."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "workers" / "discovery_worker" / "tests" / "fixtures" / "cic"
sys.path.insert(0, str(ROOT / "workers" / "discovery_worker"))
sys.path.insert(0, str(ROOT / "packages" / "agents"))

from aqa_discovery.crawl_settings import CrawlSettings
from aqa_discovery.crawler import CrawlSession


def _run_unit_tests() -> None:
    from tests.test_cic_phase2 import (
        test_discovery_flow_navigate_click_navigate,
        test_planner_includes_hash_route_links,
        test_planner_includes_modal_trigger,
        test_planner_includes_wizard_buttons,
        test_url_compare_hash_routes_differ,
    )

    test_url_compare_hash_routes_differ()
    test_planner_includes_hash_route_links()
    test_planner_includes_modal_trigger()
    test_planner_includes_wizard_buttons()
    test_discovery_flow_navigate_click_navigate()
    print("OK unit: url_compare, planner, discovery flows")


def _collect_texts(snapshot) -> set[str]:
    texts: set[str] = set()
    for state in snapshot.states:
        for element in state.elements:
            if element.text_content:
                texts.add(element.text_content)
    return texts


def _verify_modal() -> None:
    fixture = FIXTURES / "modal.html"
    settings = CrawlSettings(
        max_depth=0,
        max_pages=1,
        enable_cic=True,
        max_interactions_per_url=10,
        interaction_wait_ms=400,
    )
    with CrawlSession(headless=True) as session:
        snapshot, _ = session._visit_page(fixture.as_uri(), depth=0, settings=settings)
    texts = _collect_texts(snapshot)
    assert "Modal Secret Action" in texts, f"modal content not discovered: {sorted(texts)}"
    print(f"OK modal: states={len(snapshot.states)} secret_found=True")


def _verify_hash_spa() -> None:
    fixture = FIXTURES / "hash_spa.html"
    settings = CrawlSettings(
        max_depth=0,
        max_pages=1,
        enable_cic=True,
        max_interactions_per_url=10,
        interaction_wait_ms=400,
    )
    with CrawlSession(headless=True) as session:
        snapshot, _ = session._visit_page(fixture.as_uri(), depth=0, settings=settings)
    discovered = [item.url for item in snapshot.discovered_urls]
    state_urls = {state.url for state in snapshot.states}
    all_urls = set(discovered) | state_urls
    texts = _collect_texts(snapshot)
    assert any("#/settings" in url for url in all_urls), (
        f"hash route not discovered: urls={all_urls} discoveries={discovered}"
    )
    assert "SPA Secret Action" in texts, f"SPA panel content not found: {sorted(texts)}"
    print(f"OK hash_spa: discoveries={len(discovered)} secret_found=True")


def _verify_wizard() -> None:
    fixture = FIXTURES / "wizard.html"
    settings = CrawlSettings(
        max_depth=0,
        max_pages=1,
        enable_cic=True,
        max_interactions_per_url=10,
        interaction_wait_ms=400,
    )
    with CrawlSession(headless=True) as session:
        snapshot, _ = session._visit_page(fixture.as_uri(), depth=0, settings=settings)
    texts = _collect_texts(snapshot)
    assert "Wizard Secret Action" in texts, f"wizard step 2 not reached: {sorted(texts)}"
    print(f"OK wizard: states={len(snapshot.states)} secret_found=True")


def main() -> int:
    _run_unit_tests()
    _verify_modal()
    _verify_hash_spa()
    _verify_wizard()
    print("verify_cic_phase2: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
