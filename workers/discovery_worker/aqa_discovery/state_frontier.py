"""Global state frontier helpers for Phase 2 state-graph crawling."""

from __future__ import annotations

from aqa_discovery.cic.replay import build_replay_path
from aqa_discovery.spa_views import is_virtual_view_url
from aqa_discovery.types import (
    InteractionAction,
    PageSnapshot,
    StateFrontierItem,
    UIStateSnapshot,
)
from aqa_discovery.url_utils import normalize_crawl_url

BASELINE_FINGERPRINT = "__baseline__"


def state_visit_key(url: str, fingerprint: str | None) -> tuple[str, str]:
    """Visited-set key for a (url, ui_state) pair."""
    base = normalize_crawl_url(url.split("#")[0].rstrip("/"))
    if is_virtual_view_url(url):
        base = normalize_crawl_url(url)
    return base, fingerprint or BASELINE_FINGERPRINT


def base_page_url(url: str) -> str:
    """Strip synthetic SPA view marker from a URL."""
    if is_virtual_view_url(url):
        return url.split("#")[0].rstrip("/")
    return url


def merge_page_snapshots(existing: PageSnapshot, incoming: PageSnapshot) -> PageSnapshot:
    """Merge CIC results from multiple frontier visits to the same page URL."""
    known_state_keys = {state.state_key for state in existing.states}
    known_fingerprints = {state.fingerprint for state in existing.states if state.fingerprint}

    for state in incoming.states:
        if state.state_key in known_state_keys:
            continue
        if state.fingerprint and state.fingerprint in known_fingerprints:
            continue
        existing.states.append(state)
        known_state_keys.add(state.state_key)
        if state.fingerprint:
            known_fingerprints.add(state.fingerprint)

    known_transitions = {(t.from_state_key, t.to_state_key) for t in existing.transitions}
    for transition in incoming.transitions:
        key = (transition.from_state_key, transition.to_state_key)
        if key in known_transitions:
            continue
        existing.transitions.append(transition)
        known_transitions.add(key)

    seen_disc_urls = {item.url for item in existing.discovered_urls}
    for item in incoming.discovered_urls:
        if item.url not in seen_disc_urls:
            existing.discovered_urls.append(item)
            seen_disc_urls.add(item.url)

    if len(incoming.elements) > len(existing.elements):
        existing.elements = list(incoming.elements)
    if len(incoming.forms) > len(existing.forms):
        existing.forms = list(incoming.forms)

    existing.interaction_events.extend(incoming.interaction_events)
    if incoming.api_endpoints:
        from aqa_discovery.network_capture import merge_api_endpoints

        existing.api_endpoints = merge_api_endpoints(existing.api_endpoints, incoming.api_endpoints)
    if incoming.network_events:
        existing.network_events.extend(incoming.network_events)
    if incoming.spa_route_events:
        seen_spa = {(e.from_url, e.to_url) for e in existing.spa_route_events}
        for event in incoming.spa_route_events:
            key = (event.from_url, event.to_url)
            if key not in seen_spa:
                existing.spa_route_events.append(event)
                seen_spa.add(key)

    return existing


def _path_plus_action(
    parent_key: str,
    action: InteractionAction,
    states_by_key: dict[str, UIStateSnapshot],
) -> list[InteractionAction]:
    return build_replay_path(parent_key, states_by_key) + [action]


def collect_frontier_seeds(
    snapshot: PageSnapshot,
    links: list[str],
    *,
    page_depth: int,
    max_depth: int,
    states_budget_hit: bool,
) -> list[StateFrontierItem]:
    """Build global frontier seeds after a page visit."""
    seeds: list[StateFrontierItem] = []
    seen_seed_keys: set[tuple[str, str]] = set()
    page_url = base_page_url(snapshot.url)
    states_by_key = {state.state_key: state for state in snapshot.states}

    def _add_seed(item: StateFrontierItem) -> None:
        key = state_visit_key(item.url, item.state_fingerprint)
        if key in seen_seed_keys:
            return
        seen_seed_keys.add(key)
        seeds.append(item)

    if states_budget_hit:
        for state in snapshot.states:
            if state.interaction_depth < 1:
                continue
            _add_seed(
                StateFrontierItem(
                    url=page_url,
                    replay_path=build_replay_path(state.state_key, states_by_key),
                    state_fingerprint=state.fingerprint,
                    state_key=state.state_key,
                    page_depth=page_depth,
                    explore_children_only=True,
                    label=(state.title or state.state_key)[:80],
                )
            )

    for discovery in snapshot.discovered_urls:
        arrival_path: list[InteractionAction] = list(discovery.arrival_replay_path)
        if not arrival_path and discovery.source_state_key and discovery.trigger_interaction:
            arrival_path = _path_plus_action(
                discovery.source_state_key,
                discovery.trigger_interaction,
                states_by_key,
            )
        _add_seed(
            StateFrontierItem(
                url=discovery.url,
                replay_path=arrival_path,
                state_fingerprint=BASELINE_FINGERPRINT,
                page_depth=page_depth + 1,
                explore_children_only=False,
                label=discovery.url[:80],
            )
        )

    if page_depth < max_depth:
        for link in links:
            if is_virtual_view_url(link):
                continue
            _add_seed(
                StateFrontierItem(
                    url=link,
                    replay_path=[],
                    state_fingerprint=BASELINE_FINGERPRINT,
                    page_depth=page_depth + 1,
                )
            )

    return seeds
