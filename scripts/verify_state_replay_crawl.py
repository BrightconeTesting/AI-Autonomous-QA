#!/usr/bin/env python3
"""Verify state-based CIC — replay paths, tab context, and overlay form capture."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "workers" / "discovery_worker" / "tests" / "fixtures" / "cic"
sys.path.insert(0, str(ROOT / "workers" / "discovery_worker"))
sys.path.insert(0, str(ROOT / "packages" / "aqa_shared"))
sys.path.insert(0, str(ROOT / "packages" / "agents"))


def _run_replay_unit_tests() -> None:
    from aqa_discovery.cic.replay import build_replay_path
    from aqa_discovery.types import InteractionAction, UIStateSnapshot

    click_tab = InteractionAction(
        action_type="click",
        interaction_key="tab|Details",
        text_content="Details",
        role="tab",
    )
    open_modal = InteractionAction(
        action_type="click",
        interaction_key="btn|Add",
        text_content="Add item",
        role="button",
    )
    baseline = UIStateSnapshot(
        state_key="s_baseline",
        url="https://example.com",
        title="Test",
        fingerprint="fp0",
        interaction_depth=0,
    )
    tab_state = UIStateSnapshot(
        state_key="s_tab",
        parent_state_key="s_baseline",
        trigger_interaction=click_tab,
        url="https://example.com",
        title="Test",
        fingerprint="fp1",
        interaction_depth=1,
    )
    modal_state = UIStateSnapshot(
        state_key="s_modal",
        parent_state_key="s_tab",
        trigger_interaction=open_modal,
        url="https://example.com",
        title="Test",
        fingerprint="fp2",
        interaction_depth=2,
    )
    states = {
        "s_baseline": baseline,
        "s_tab": tab_state,
        "s_modal": modal_state,
    }
    path = build_replay_path("s_modal", states)
    assert len(path) == 2
    assert path[0].text_content == "Details"
    assert path[1].text_content == "Add item"
    print("OK unit: build_replay_path")


def _run_catalog_unit_tests() -> None:
    from aqa_shared.discovery.test_data_discovery import build_replay_steps_for_state, build_test_data_catalog

    states = [
        {
            "state_id": "uuid-baseline",
            "state_key": "s_base",
            "parent_state_key": None,
            "trigger_action": {},
        },
        {
            "state_id": "uuid-modal",
            "state_key": "s_modal",
            "parent_state_key": "s_base",
            "trigger_action": {"action_type": "click", "text_content": "Add item", "role": "button"},
        },
    ]
    steps = build_replay_steps_for_state("s_modal", {s["state_key"]: s for s in states})
    assert len(steps) == 1
    assert steps[0]["text_content"] == "Add item"

    catalog = build_test_data_catalog(
        forms=[
            {
                "form_id": "form-1",
                "state_id": "uuid-modal",
                "field_element_ids": ["el-1"],
                "attributes": {"overlay_type": "dialog"},
                "name": "Add item",
            }
        ],
        elements=[
            {
                "element_id": "el-1",
                "attributes": {"name": "item_name", "type": "text"},
            }
        ],
        api_endpoints=[],
        states=states,
        run_id="verify-run",
    )
    assert len(catalog) == 1
    entry = catalog[0]
    assert entry.get("state_key") == "s_modal"
    assert entry.get("replay_steps")
    assert entry["fields"][0]["suggested_safe_value"].startswith("qa-")
    print("OK unit: state-aware test_data_catalog")


def _collect_texts(snapshot) -> set[str]:
    texts: set[str] = set()
    for state in snapshot.states:
        for element in state.elements:
            if element.text_content:
                texts.add(element.text_content.strip())
    return texts


def _visit(fixture_name: str, *, state_replay: bool):
    from aqa_discovery.crawl_settings import CrawlSettings
    from aqa_discovery.crawler import CrawlSession

    fixture = FIXTURES / fixture_name
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
        cic_in_page_only=True,
        cic_state_replay=state_replay,
        cic_level_bfs=state_replay,
        cic_context_scoped_dedup=state_replay,
        cic_virtual_forms=state_replay,
        cic_replay_verify_fingerprint=state_replay,
        safe_form_fill=False,
    )
    with CrawlSession(headless=True) as session:
        return session._visit_page(fixture.as_uri(), depth=0, settings=settings)


def _verify_tab_context() -> None:
    legacy, _ = _visit("tabs.html", state_replay=False)
    replay, _ = _visit("tabs.html", state_replay=True)

    legacy_texts = _collect_texts(legacy)
    replay_texts = _collect_texts(replay)
    assert "Secret Action" in replay_texts, f"state replay missed tab content: {sorted(replay_texts)}"
    assert len(replay.states) >= len(legacy.states)
    assert len(replay.transitions) >= 1
    print(f"OK tabs: legacy_states={len(legacy.states)} replay_states={len(replay.states)} secret_found=True")


def _verify_tab_modal_form() -> None:
    snapshot, _ = _visit("tab_modal_form.html", state_replay=True)
    texts = _collect_texts(snapshot)
    assert "Save item" in texts, f"modal action not found: {sorted(texts)}"

    depth2_states = [state for state in snapshot.states if state.interaction_depth >= 2]
    assert depth2_states, "expected depth-2 modal state"

    modal_forms = []
    for state in depth2_states:
        modal_forms.extend(state.forms)
    assert modal_forms, "expected virtual form in modal state"
    field_count = sum(len(form.field_xpaths) for form in modal_forms)
    assert field_count >= 3, f"expected modal fields, got {field_count}"

    print(
        f"OK tab_modal_form: states={len(snapshot.states)} "
        f"depth2={len(depth2_states)} modal_fields={field_count}"
    )


def main() -> int:
    print("verify:state-replay-crawl")
    _run_replay_unit_tests()
    _run_catalog_unit_tests()
    _verify_tab_context()
    _verify_tab_modal_form()
    print("verify:state-replay-crawl OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
