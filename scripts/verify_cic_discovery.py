#!/usr/bin/env python3
"""Verify CIC Phase 1 — tabs/accordions, states, enable_cic flag."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "workers" / "discovery_worker"))

from aqa_discovery.crawl_settings import CrawlSettings
from aqa_discovery.crawler import CrawlSession
from aqa_discovery.cic.fingerprint import compute_state_fingerprint
from aqa_discovery.extractors import diff_elements
from aqa_discovery.types import ElementSnapshot


FIXTURE = ROOT / "workers" / "discovery_worker" / "tests" / "fixtures" / "cic" / "tabs.html"
FIXTURE_URL = FIXTURE.as_uri()


def _verify_unit_modules() -> None:
    sys.path.insert(0, str(ROOT / "workers" / "discovery_worker"))
    from tests.test_cic_phase1 import (
        test_fingerprint_differs_when_elements_change,
        test_fingerprint_stable_for_same_elements,
        test_planner_prioritizes_tabs,
        test_safety_blocks_file_input,
        test_safety_blocks_logout,
    )

    test_fingerprint_stable_for_same_elements()
    test_fingerprint_differs_when_elements_change()
    test_safety_blocks_logout()
    test_safety_blocks_file_input()
    test_planner_prioritizes_tabs()
    print("OK unit: fingerprint, safety, planner")


def _verify_diff_elements() -> None:
    before = [ElementSnapshot(tag_name="button", role="tab", text_content="Overview", is_visible=True)]
    after = before + [
        ElementSnapshot(tag_name="button", role="button", text_content="Secret Action", is_visible=True)
    ]
    new = diff_elements(before, after)
    assert len(new) == 1
    assert new[0].text_content == "Secret Action"
    print("OK diff_elements")


def _verify_cic_disabled_regression() -> None:
    settings = CrawlSettings(max_depth=0, max_pages=1, enable_cic=False)
    with CrawlSession(headless=True) as session:
        snapshot, links = session._visit_page(FIXTURE_URL, depth=0, settings=settings)
    assert not snapshot.states
    assert not snapshot.transitions
    print("OK regression: enable_cic=false has no states")


def _verify_cic_enabled() -> None:
    if not FIXTURE.is_file():
        print("SKIP integration: fixture not found")
        return

    settings = CrawlSettings(
        max_depth=0,
        max_pages=1,
        enable_cic=True,
        max_states_per_url=10,
        max_interactions_per_url=15,
        max_interactions_per_state=5,
        interaction_wait_ms=500,
    )
    with CrawlSession(headless=True) as session:
        snapshot, _links = session._visit_page(FIXTURE_URL, depth=0, settings=settings)

    assert len(snapshot.states) >= 2, f"expected >=2 states, got {len(snapshot.states)}"

    all_element_texts: set[str] = set()
    for state in snapshot.states:
        for el in state.elements:
            if el.text_content:
                all_element_texts.add(el.text_content)

    assert "Secret Action" in all_element_texts or len(snapshot.transitions) >= 1, (
        "CIC should discover hidden tab content or record transitions"
    )
    print(
        f"OK CIC: states={len(snapshot.states)} transitions={len(snapshot.transitions)} "
        f"elements_sample={sorted(all_element_texts)[:5]}"
    )


def main() -> int:
    _verify_unit_modules()
    _verify_diff_elements()
    _verify_cic_disabled_regression()
    _verify_cic_enabled()
    print("verify_cic_discovery: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
