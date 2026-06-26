#!/usr/bin/env python3
"""Verify Phase 2 global state-graph crawling."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "workers" / "discovery_worker" / "tests" / "fixtures" / "cic"
sys.path.insert(0, str(ROOT / "workers" / "discovery_worker"))
sys.path.insert(0, str(ROOT / "packages" / "aqa_shared"))


def _run_frontier_unit_tests() -> None:
    from aqa_discovery.state_frontier import (
        BASELINE_FINGERPRINT,
        collect_frontier_seeds,
        merge_page_snapshots,
        state_visit_key,
    )
    from aqa_discovery.types import InteractionAction, PageSnapshot, UIStateSnapshot

    key = state_visit_key("https://example.com/app", BASELINE_FINGERPRINT)
    assert key == ("https://example.com/app", BASELINE_FINGERPRINT)

    baseline = PageSnapshot(
        url="https://example.com",
        title="A",
        status=200,
        html_length=100,
        depth=0,
        states=[
            UIStateSnapshot(
                state_key="s0",
                url="https://example.com",
                title="A",
                fingerprint="fp0",
                interaction_depth=0,
            ),
            UIStateSnapshot(
                state_key="s1",
                url="https://example.com",
                title="A",
                parent_state_key="s0",
                fingerprint="fp1",
                interaction_depth=1,
                trigger_interaction=InteractionAction(
                    action_type="click",
                    interaction_key="tab",
                    text_content="Items",
                    role="tab",
                ),
            )
        ],
    )
    seeds = collect_frontier_seeds(
        baseline,
        links=["https://example.com/other"],
        page_depth=0,
        max_depth=2,
        states_budget_hit=True,
    )
    assert any(seed.replay_path for seed in seeds)
    assert any(seed.url == "https://example.com/other" for seed in seeds)

    incoming = PageSnapshot(
        url="https://example.com",
        title="A",
        status=200,
        html_length=100,
        depth=0,
        states=[
            UIStateSnapshot(
                state_key="s2",
                url="https://example.com",
                title="A",
                fingerprint="fp2",
                interaction_depth=2,
            )
        ],
    )
    merged = merge_page_snapshots(baseline, incoming)
    assert len(merged.states) == 3
    print("OK unit: state_frontier helpers")


def _crawl(fixture_name: str, *, global_graph: bool):
    from aqa_discovery.crawl_settings import CrawlSettings
    from aqa_discovery.crawler import CrawlSession

    settings = CrawlSettings(
        max_depth=0,
        max_pages=1,
        enable_cic=True,
        cic_mode="full",
        cic_rich_interactions=True,
        interaction_wait_ms=400,
        max_interactions_per_url=20,
        max_interactions_per_state=8,
        max_interaction_depth=4,
        cic_state_replay=True,
        cic_level_bfs=True,
        cic_virtual_forms=True,
        cic_global_state_graph=global_graph,
        respect_robots_txt=False,
    )
    fixture = FIXTURES / fixture_name
    with CrawlSession(headless=True) as session:
        return session.crawl_bfs([fixture.as_uri()], settings)


def _verify_global_graph_tab_modal() -> None:
    result = _crawl("tab_modal_form.html", global_graph=True)
    assert result.pages, "expected at least one page"
    page = result.pages[0]
    depth2 = [s for s in page.states if s.interaction_depth >= 2]
    assert depth2, "expected depth-2 modal state via global graph"
    modal_forms = [form for state in depth2 for form in state.forms]
    assert modal_forms, "expected forms captured in modal state"
    print(
        f"OK global_graph: pages={len(result.pages)} states={len(page.states)} "
        f"depth2={len(depth2)} forms={len(modal_forms)}"
    )


def _verify_arrival_path_on_discovery() -> None:
    from aqa_discovery.cic.replay import build_replay_path
    from aqa_discovery.types import InteractionAction, UIStateSnapshot

    from aqa_discovery.cic.session import _arrival_path_for_discovery

    tab = InteractionAction(action_type="click", interaction_key="t", text_content="Items", role="tab")
    open_modal = InteractionAction(
        action_type="click", interaction_key="m", text_content="Add item", role="button"
    )
    states = {
        "s0": UIStateSnapshot(state_key="s0", url="https://x.com", title="", interaction_depth=0),
        "s1": UIStateSnapshot(
            state_key="s1",
            parent_state_key="s0",
            trigger_interaction=tab,
            url="https://x.com",
            title="",
            interaction_depth=1,
        ),
        "s2": UIStateSnapshot(
            state_key="s2",
            parent_state_key="s1",
            trigger_interaction=open_modal,
            url="https://x.com",
            title="",
            interaction_depth=2,
        ),
    }
    path = _arrival_path_for_discovery("s1", open_modal, states)
    assert len(path) == 2
    assert path[0].text_content == "Items"
    assert build_replay_path("s2", states)[1].text_content == "Add item"
    print("OK arrival_replay_path provenance")


def main() -> int:
    print("verify:state-graph-crawl")
    _run_frontier_unit_tests()
    _verify_arrival_path_on_discovery()
    _verify_global_graph_tab_modal()
    print("verify:state-graph-crawl OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
