#!/usr/bin/env python3
"""Verify CIC Phase 4 — transition-graph flows, tables, date pickers, AppMap v2."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "workers" / "discovery_worker" / "tests" / "fixtures" / "cic"
sys.path.insert(0, str(ROOT / "workers" / "discovery_worker"))
sys.path.insert(0, str(ROOT / "packages" / "agents"))


def _run_unit_tests() -> None:
    from tests.test_cic_phase4 import (
        test_graph_flow_builder,
        test_interaction_step_preserves_action_type,
        test_planner_date_picker,
        test_planner_table_pagination,
        test_transition_graph_paths,
    )

    test_interaction_step_preserves_action_type()
    test_transition_graph_paths()
    test_graph_flow_builder()
    test_planner_table_pagination()
    test_planner_date_picker()
    print("OK unit: transition graph, table/date planner")


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

    settings = CrawlSettings(
        max_depth=0,
        max_pages=1,
        enable_cic=True,
        cic_rich_interactions=True,
        cic_enable_tables=True,
        cic_enable_date_pickers=True,
        cic_in_page_only=False,
        interaction_wait_ms=400,
        max_interactions_per_url=15,
        max_interactions_per_state=6,
        **settings_kwargs,
    )
    with CrawlSession(headless=True) as session:
        return session._visit_page((FIXTURES / fixture_name).resolve().as_uri(), depth=0, settings=settings)


def _verify_table() -> None:
    snapshot, _ = _visit("table.html")
    texts = _collect_texts(snapshot)
    assert "Secret Row Action" in texts, f"paginated row not found: {sorted(texts)}"
    print(f"OK table: states={len(snapshot.states)} transitions={len(snapshot.transitions)}")


def _verify_date_picker() -> None:
    snapshot, _ = _visit("date_picker.html")
    texts = _collect_texts(snapshot)
    assert "Secret Day Cell" in texts, f"calendar cells not found: {sorted(texts)}"
    print(f"OK date_picker: states={len(snapshot.states)} transitions={len(snapshot.transitions)}")


def _verify_graph_flows() -> None:
    from aqa_agents.discovery.flows import build_flows_from_states

    pages = [{"page_id": "p1", "url": "https://example.com", "title": "T"}]
    states = [
        {"state_id": "a", "page_id": "p1", "state_key": "s0", "interaction_depth": 0, "parent_state_key": None},
        {"state_id": "b", "page_id": "p1", "state_key": "s1", "interaction_depth": 1, "parent_state_key": "s0"},
        {"state_id": "c", "page_id": "p1", "state_key": "s2", "interaction_depth": 1, "parent_state_key": "s0"},
    ]
    transitions = [
        {"from_state_id": "a", "to_state_id": "b", "action": {"action_type": "click"}},
        {"from_state_id": "a", "to_state_id": "c", "action": {"action_type": "hover"}},
    ]
    flows = build_flows_from_states(pages, states, transitions)
    assert len(flows) == 2
    actions = {flow["steps"][1]["action"] for flow in flows}
    assert actions == {"click", "hover"}
    print("OK graph_flows: 2 paths with click + hover action types")


def _verify_appmap_v2_schema() -> None:
    from aqa_agents.discovery.appmap import build_appmap_document

    doc = build_appmap_document(
        application_id="00000000-0000-0000-0000-000000000001",
        last_crawl_at=None,
        pages=[],
        elements=[],
        flows=[],
        states=[{"state_id": "s1", "page_id": "p1", "state_key": "root"}],
        transitions=[],
    )
    assert doc["schema_version"] == 2
    assert "states" in doc
    print("OK appmap_v2: schema_version=2 with states")


def main() -> int:
    _run_unit_tests()
    _verify_graph_flows()
    _verify_appmap_v2_schema()
    _verify_table()
    _verify_date_picker()
    print("verify_cic_phase4: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
