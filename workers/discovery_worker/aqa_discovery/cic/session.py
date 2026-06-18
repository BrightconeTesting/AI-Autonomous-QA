"""CIC session loop — scan, interact, snapshot, repeat (Phase 1–3)."""

from __future__ import annotations

import logging
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from aqa_discovery.cic.executor import execute_interaction
from aqa_discovery.cic.fingerprint import compute_state_fingerprint, state_key_from_fingerprint
from aqa_discovery.cic.planner import plan_interactions
from aqa_discovery.cic.recovery import recover_after_interaction, recover_to_baseline
from aqa_discovery.cic.scope import CicScope, iter_cic_scopes
from aqa_discovery.cic.url_compare import (
    is_at_baseline,
    is_url_discovery,
    navigated_away_from_baseline,
    normalize_discovery_url,
)
from aqa_discovery.crawl_settings import CrawlSettings
from aqa_discovery.extractors import detect_dialog_titles, diff_elements, extract_elements, save_page_screenshot
from aqa_discovery.interaction_safety import build_interaction_key, is_safe_to_interact
from aqa_discovery.persist import screenshot_path_for_state
from aqa_discovery.types import (
    CrawlStats,
    DiscoveredUrl,
    InteractionAction,
    StateTransition,
    UIStateSnapshot,
)

logger = logging.getLogger(__name__)


@dataclass
class CicSessionResult:
    states: list[UIStateSnapshot] = field(default_factory=list)
    transitions: list[StateTransition] = field(default_factory=list)
    discovered_urls: list[DiscoveredUrl] = field(default_factory=list)
    baseline_elements: list = field(default_factory=list)
    all_links: set[str] = field(default_factory=set)


def _make_state_snapshot(
    scope: CicScope,
    *,
    status: int,
    parent_state_key: str | None,
    trigger: InteractionAction | None,
    depth: int,
    app_id: uuid.UUID | None,
    capture_artifacts: bool,
    baseline_url: str,
    screenshot_all_states: bool,
) -> UIStateSnapshot | None:
    elements = extract_elements(scope.page, scope=None if scope.is_main else scope)
    dialogs = detect_dialog_titles(scope.page)
    title = scope.page.title()
    current_url = scope.page.url
    fingerprint = compute_state_fingerprint(
        url=current_url,
        title=title,
        elements=elements,
        dialog_titles=dialogs,
    )
    if scope.frame_name and scope.frame_name != "main":
        fingerprint = compute_state_fingerprint(
            url=current_url,
            title=title,
            elements=elements,
            dialog_titles=dialogs + [f"frame:{scope.frame_name}"],
        )
    state_key = state_key_from_fingerprint(fingerprint)

    screenshot_path: str | None = None
    should_capture = capture_artifacts and app_id is not None and (screenshot_all_states or depth == 0)
    if should_capture and scope.is_main:
        dest = screenshot_path_for_state(app_id=app_id, url=baseline_url, state_key=state_key)
        save_page_screenshot(scope.page, dest)
        screenshot_path = str(dest)

    return UIStateSnapshot(
        state_key=state_key,
        parent_state_key=parent_state_key,
        trigger_interaction=trigger,
        url=current_url,
        title=title,
        status=status,
        html_length=0,
        interaction_depth=depth,
        elements=elements,
        screenshot_path=screenshot_path,
        fingerprint=fingerprint,
    )


def run_cic_session(
    page,
    *,
    baseline_url: str,
    status: int,
    settings: CrawlSettings,
    stats: CrawlStats,
    app_id: uuid.UUID | None = None,
    capture_artifacts: bool = False,
    extract_links_fn: Callable | None = None,
    detect_blockers: Callable | None = None,
) -> CicSessionResult:
    """Explore in-page UI states via safe interactions across main page and same-origin frames."""
    result = CicSessionResult()
    screenshot_all = settings.cic_screenshot_all_states or settings.cic_mode == "full"

    for scope in iter_cic_scopes(page, include_iframes=settings.cic_enable_iframes):
        _run_cic_on_scope(
            scope,
            result=result,
            baseline_url=baseline_url,
            status=status,
            settings=settings,
            stats=stats,
            app_id=app_id,
            capture_artifacts=capture_artifacts,
            screenshot_all_states=screenshot_all,
            extract_links_fn=extract_links_fn if scope.is_main else None,
            detect_blockers=detect_blockers,
        )

    return result


def _run_cic_on_scope(
    scope: CicScope,
    *,
    result: CicSessionResult,
    baseline_url: str,
    status: int,
    settings: CrawlSettings,
    stats: CrawlStats,
    app_id: uuid.UUID | None,
    capture_artifacts: bool,
    screenshot_all_states: bool,
    extract_links_fn: Callable | None,
    detect_blockers: Callable | None,
) -> None:
    known_fingerprints: set[str] = set()
    interacted: set[str] = set()
    interactions_this_url = 0
    interactions_this_state: dict[str, int] = {}

    baseline = _make_state_snapshot(
        scope,
        status=status,
        parent_state_key=None,
        trigger=None,
        depth=0,
        app_id=app_id,
        capture_artifacts=capture_artifacts,
        baseline_url=baseline_url,
        screenshot_all_states=screenshot_all_states,
    )
    if baseline is None:
        return

    known_fingerprints.add(baseline.fingerprint or "")
    result.states.append(baseline)
    if scope.is_main:
        result.baseline_elements = list(baseline.elements)
    stats.states_discovered += 1

    if extract_links_fn and scope.is_main:
        result.all_links.update(extract_links_fn(scope.page, baseline_url))

    queue: deque[tuple[str, InteractionAction, str, int]] = deque()
    _enqueue_actions(queue, baseline, scope.page.url, settings, interacted)

    while queue and len(result.states) < settings.max_states_per_url:
        if stats.states_discovered >= settings.max_states_total:
            break
        if interactions_this_url >= settings.max_interactions_per_url:
            break

        parent_key, action, page_url, depth = queue.popleft()

        if depth >= settings.max_interaction_depth:
            continue

        state_interactions = interactions_this_state.get(parent_key, 0)
        if state_interactions >= settings.max_interactions_per_state:
            continue

        safe, reason = is_safe_to_interact(
            _action_to_element(action),
            page_url=page_url,
            blocked_patterns=settings.blocked_interaction_patterns,
            allow_form_fill=settings.safe_form_fill,
        )
        if not safe:
            stats.skipped_interaction_safety += 1
            continue

        if scope.is_main and not is_at_baseline(scope.page.url, baseline_url):
            recover_to_baseline(scope.page, baseline_url, page_timeout_ms=settings.page_timeout_ms)

        pre_url = scope.page.url
        try:
            if detect_blockers and scope.is_main:
                detect_blockers(scope.page)
            post_url = execute_interaction(scope, action, settings)
            if detect_blockers and scope.is_main:
                detect_blockers(scope.page)
        except Exception as exc:
            logger.debug(
                "CIC interaction failed",
                extra={"key": action.interaction_key, "type": action.action_type, "error": str(exc)},
            )
            if scope.is_main:
                recover_after_interaction(
                    scope.page,
                    baseline_url,
                    page_timeout_ms=settings.page_timeout_ms,
                    navigated_away=navigated_away_from_baseline(scope.page.url, baseline_url),
                )
            continue

        interactions_this_url += 1
        interactions_this_state[parent_key] = state_interactions + 1
        stats.interactions_executed += 1
        interacted.add(action.interaction_key)

        navigated_away = navigated_away_from_baseline(post_url, baseline_url)
        if scope.is_main and is_url_discovery(pre_url, post_url, baseline_url):
            result.discovered_urls.append(
                DiscoveredUrl(
                    url=normalize_discovery_url(post_url),
                    discovered_via="interaction",
                    source_page_url=baseline_url,
                    source_state_key=parent_key,
                    trigger_interaction=action,
                )
            )

        new_state = _make_state_snapshot(
            scope,
            status=status,
            parent_state_key=parent_key,
            trigger=action,
            depth=depth + 1,
            app_id=app_id,
            capture_artifacts=capture_artifacts,
            baseline_url=baseline_url,
            screenshot_all_states=screenshot_all_states,
        )
        if new_state is None:
            if scope.is_main:
                recover_after_interaction(
                    scope.page,
                    baseline_url,
                    page_timeout_ms=settings.page_timeout_ms,
                    navigated_away=navigated_away,
                )
            continue

        if new_state.fingerprint in known_fingerprints:
            stats.skipped_duplicate_state += 1
            if scope.is_main and navigated_away:
                recover_after_interaction(
                    scope.page,
                    baseline_url,
                    page_timeout_ms=settings.page_timeout_ms,
                    navigated_away=True,
                )
            continue

        known_fingerprints.add(new_state.fingerprint or "")
        result.states.append(new_state)
        result.transitions.append(
            StateTransition(from_state_key=parent_key, to_state_key=new_state.state_key, action=action)
        )
        stats.states_discovered += 1

        if extract_links_fn and scope.is_main:
            result.all_links.update(extract_links_fn(scope.page, baseline_url))

        baseline_ref = result.baseline_elements if scope.is_main else baseline.elements
        new_only = diff_elements(baseline_ref, new_state.elements)
        _enqueue_actions(queue, new_state, scope.page.url, settings, interacted, seed_elements=new_only)

        if scope.is_main:
            recover_after_interaction(
                scope.page,
                baseline_url,
                page_timeout_ms=settings.page_timeout_ms,
                navigated_away=navigated_away,
            )


def _enqueue_actions(
    queue: deque,
    state: UIStateSnapshot,
    page_url: str,
    settings: CrawlSettings,
    interacted: set[str],
    *,
    seed_elements: list | None = None,
) -> None:
    elements = seed_elements if seed_elements is not None else state.elements
    actions = plan_interactions(
        elements,
        page_url=page_url,
        blocked_patterns=settings.blocked_interaction_patterns,
        already_interacted=interacted,
        in_page_only=settings.cic_in_page_only,
        max_candidates=settings.max_interactions_per_state,
        safe_form_fill=settings.safe_form_fill,
        rich_interactions=settings.cic_rich_interactions,
        enable_tables=settings.cic_enable_tables,
        enable_date_pickers=settings.cic_enable_date_pickers,
    )
    for action in actions:
        queue.append((state.state_key, action, page_url, state.interaction_depth))


def _action_to_element(action: InteractionAction):
    from aqa_discovery.types import ElementSnapshot

    return ElementSnapshot(
        tag_name="unknown",
        role=action.role,
        text_content=action.text_content,
        semantic_selector=action.semantic_selector,
        xpath_fallback=action.xpath_fallback,
        interaction_key=action.interaction_key,
        is_visible=True,
    )
