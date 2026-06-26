"""CIC session loop — scan, interact, snapshot, repeat (Phase 1–3)."""

from __future__ import annotations

import logging
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from aqa_discovery.cic.executor import execute_interaction
from aqa_discovery.cic.fingerprint import compute_state_fingerprint, state_key_from_fingerprint
from aqa_discovery.cic.planner import plan_interactions
from aqa_discovery.cic.recovery import recover_after_interaction, recover_to_baseline
from aqa_discovery.cic.replay import build_replay_path, replay_to_state
from aqa_discovery.cic.scope import CicScope, iter_cic_scopes
from aqa_discovery.cic.url_compare import (
    is_at_baseline,
    is_url_discovery,
    navigated_away_from_baseline,
    normalize_discovery_url,
)
from aqa_discovery.crawl_settings import CrawlSettings
from aqa_discovery.extractors import detect_dialog_titles, diff_elements, save_page_screenshot
from aqa_discovery.page_capture import capture_interactive_data
from aqa_discovery.interaction_safety import build_interaction_key, is_safe_to_interact
from aqa_discovery.persist import screenshot_path_for_state
from aqa_discovery.api_types import InteractionEventSnapshot
from aqa_discovery.types import (
    CrawlStats,
    DiscoveredUrl,
    InteractionAction,
    StateTransition,
    UIStateSnapshot,
)

logger = logging.getLogger(__name__)


def _arrival_path_for_discovery(
    parent_key: str,
    action: InteractionAction,
    states_by_key: dict[str, UIStateSnapshot],
) -> list[InteractionAction]:
    return build_replay_path(parent_key, states_by_key) + [action]


@dataclass
class CicSessionResult:
    states: list[UIStateSnapshot] = field(default_factory=list)
    transitions: list[StateTransition] = field(default_factory=list)
    discovered_urls: list[DiscoveredUrl] = field(default_factory=list)
    interaction_events: list[InteractionEventSnapshot] = field(default_factory=list)
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
    allowed_domains: list[str] | None = None,
    include_virtual_forms: bool = False,
) -> UIStateSnapshot | None:
    elements, forms = capture_interactive_data(
        scope.page,
        scope=None if scope.is_main else scope,
        page_url=scope.page.url,
        allowed_domains=allowed_domains,
        include_virtual_forms=include_virtual_forms,
    )
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
        forms=forms,
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
    on_progress: Callable[[str, CrawlStats, dict], None] | None = None,
    session_start: float | None = None,
    explore_children_only: bool = False,
    entry_depth: int = 0,
) -> CicSessionResult:
    """Explore in-page UI states via safe interactions across main page and same-origin frames."""
    result = CicSessionResult()
    screenshot_all = settings.cic_screenshot_all_states or settings.cic_mode == "full"
    started_at = session_start if session_start is not None else time.monotonic()

    for scope in iter_cic_scopes(page, include_iframes=settings.cic_enable_iframes):
        if explore_children_only and scope.is_main:
            entry = _make_state_snapshot(
                scope,
                status=status,
                parent_state_key=None,
                trigger=None,
                depth=entry_depth,
                app_id=app_id,
                capture_artifacts=capture_artifacts,
                baseline_url=baseline_url,
                screenshot_all_states=screenshot_all,
                allowed_domains=settings.allowed_domains,
                include_virtual_forms=settings.cic_virtual_forms,
            )
            if entry is None:
                continue
            _run_cic_on_scope_state_bfs(
                scope,
                result=result,
                baseline_url=baseline_url,
                status=status,
                settings=settings,
                stats=stats,
                app_id=app_id,
                capture_artifacts=capture_artifacts,
                screenshot_all_states=screenshot_all,
                extract_links_fn=extract_links_fn,
                detect_blockers=detect_blockers,
                on_progress=on_progress,
                session_start=started_at,
                entry_state=entry,
            )
            continue

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
            on_progress=on_progress,
            session_start=started_at,
        )

    return result


def _view_label_from_action(action: InteractionAction) -> str:
    text = (action.text_content or "").strip()
    if text:
        return text[:80]
    if action.semantic_selector:
        return action.semantic_selector[:80]
    return action.interaction_key[:80]


def _emit_cic_progress(
    on_progress: Callable[[str, CrawlStats, dict], None] | None,
    current_url: str,
    stats: CrawlStats,
    *,
    force: bool = False,
    last_emit_at: list[float],
    **payload: str,
) -> None:
    if on_progress is None:
        return
    now = time.monotonic()
    if not force and now - last_emit_at[0] < 0.75:
        return
    last_emit_at[0] = now
    on_progress(current_url, stats, payload)


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
    on_progress: Callable[[str, CrawlStats, dict], None] | None = None,
    session_start: float = 0.0,
) -> None:
    if settings.cic_state_replay and settings.cic_level_bfs:
        _run_cic_on_scope_state_bfs(
            scope,
            result=result,
            baseline_url=baseline_url,
            status=status,
            settings=settings,
            stats=stats,
            app_id=app_id,
            capture_artifacts=capture_artifacts,
            screenshot_all_states=screenshot_all_states,
            extract_links_fn=extract_links_fn,
            detect_blockers=detect_blockers,
            on_progress=on_progress,
            session_start=session_start,
        )
        return

    _run_cic_on_scope_legacy(
        scope,
        result=result,
        baseline_url=baseline_url,
        status=status,
        settings=settings,
        stats=stats,
        app_id=app_id,
        capture_artifacts=capture_artifacts,
        screenshot_all_states=screenshot_all_states,
        extract_links_fn=extract_links_fn,
        detect_blockers=detect_blockers,
        on_progress=on_progress,
        session_start=session_start,
    )


def _run_cic_on_scope_legacy(
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
    on_progress: Callable[[str, CrawlStats, dict], None] | None = None,
    session_start: float = 0.0,
) -> None:
    known_fingerprints: set[str] = set()
    interacted: set[str] = set()
    interactions_this_url = 0
    interactions_this_state: dict[str, int] = {}
    last_emit_at = [0.0]

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
        allowed_domains=settings.allowed_domains,
    )
    if baseline is None:
        return

    known_fingerprints.add(baseline.fingerprint or "")
    result.states.append(baseline)
    if scope.is_main:
        result.baseline_elements = list(baseline.elements)
    stats.states_discovered += 1
    _emit_cic_progress(
        on_progress,
        scope.page.url,
        stats,
        force=True,
        last_emit_at=last_emit_at,
        phase="cic_baseline",
        view_label=(baseline.title or baseline_url)[:80],
    )

    if extract_links_fn and scope.is_main:
        links = extract_links_fn(scope.page, baseline_url)
        result.all_links.update(links)
        for i, link in enumerate(sorted(links)):
            if i >= 20:
                break
            _emit_cic_progress(
                on_progress,
                scope.page.url,
                stats,
                force=i < 3,
                last_emit_at=last_emit_at,
                phase="link_extract",
                discovered_url=link,
            )

    queue: deque[tuple[str, InteractionAction, str, int]] = deque()
    _enqueue_actions(queue, baseline, scope.page.url, settings, interacted)

    while queue and len(result.states) < settings.max_states_per_url:
        if stats.states_discovered >= settings.max_states_total:
            break
        if (
            not settings.cic_unlimited_interactions
            and interactions_this_url >= settings.max_interactions_per_url
        ):
            break

        parent_key, action, page_url, depth = queue.popleft()

        if not settings.cic_unlimited_interactions and depth >= settings.max_interaction_depth:
            continue

        state_interactions = interactions_this_state.get(parent_key, 0)
        if (
            not settings.cic_unlimited_interactions
            and state_interactions >= settings.max_interactions_per_state
        ):
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
        result.interaction_events.append(
            InteractionEventSnapshot(
                timestamp_ms=(time.monotonic() - session_start) * 1000.0,
                interaction_key=action.interaction_key,
                action_type=action.action_type,
                semantic_selector=action.semantic_selector,
                text_content=action.text_content,
                trigger_action=action.model_dump(),
            )
        )
        if stats.interactions_executed % 5 == 0:
            _emit_cic_progress(
                on_progress,
                scope.page.url,
                stats,
                last_emit_at=last_emit_at,
                phase="cic_interaction",
            )

        navigated_away = navigated_away_from_baseline(post_url, baseline_url)
        if scope.is_main and is_url_discovery(pre_url, post_url, baseline_url):
            discovered = normalize_discovery_url(post_url)
            states_by_key = {state.state_key: state for state in result.states}
            result.discovered_urls.append(
                DiscoveredUrl(
                    url=discovered,
                    discovered_via="interaction",
                    source_page_url=baseline_url,
                    source_state_key=parent_key,
                    trigger_interaction=action,
                    arrival_replay_path=_arrival_path_for_discovery(parent_key, action, states_by_key),
                )
            )
            _emit_cic_progress(
                on_progress,
                post_url,
                stats,
                force=True,
                last_emit_at=last_emit_at,
                phase="url_discovery",
                discovered_url=discovered,
                view_label=_view_label_from_action(action),
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
            allowed_domains=settings.allowed_domains,
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
        _emit_cic_progress(
            on_progress,
            scope.page.url,
            stats,
            force=True,
            last_emit_at=last_emit_at,
            phase="new_state",
            view_label=_view_label_from_action(action),
        )

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


def _interaction_dedup_key(
    interaction_key: str,
    parent_state_key: str,
    *,
    context_scoped: bool,
) -> str:
    if context_scoped:
        return f"{parent_state_key}::{interaction_key}"
    return interaction_key


def _run_cic_on_scope_state_bfs(
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
    on_progress: Callable[[str, CrawlStats, dict], None] | None = None,
    session_start: float = 0.0,
    entry_state: UIStateSnapshot | None = None,
) -> None:
    """Level-by-level state BFS with replay paths to preserve UI context."""
    known_fingerprints: set[str] = set()
    interacted: set[str] = set()
    interactions_this_url = 0
    interactions_this_state: dict[str, int] = {}
    last_emit_at = [0.0]
    states_by_key: dict[str, UIStateSnapshot] = {}
    context_scoped = settings.cic_context_scoped_dedup
    include_virtual = settings.cic_virtual_forms

    if entry_state is not None:
        baseline = entry_state
        known_fingerprints.add(baseline.fingerprint or "")
        states_by_key[baseline.state_key] = baseline
        if not any(state.state_key == baseline.state_key for state in result.states):
            result.states.append(baseline)
            stats.states_discovered += 1
        if scope.is_main and not result.baseline_elements:
            result.baseline_elements = list(baseline.elements)
        if extract_links_fn and scope.is_main:
            result.all_links.update(extract_links_fn(scope.page, baseline_url))
        frontiers: dict[int, list[str]] = {baseline.interaction_depth: [baseline.state_key]}
        baseline_ref = baseline.elements
    else:
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
            allowed_domains=settings.allowed_domains,
            include_virtual_forms=include_virtual,
        )
        if baseline is None:
            return

        known_fingerprints.add(baseline.fingerprint or "")
        states_by_key[baseline.state_key] = baseline
        result.states.append(baseline)
        if scope.is_main:
            result.baseline_elements = list(baseline.elements)
        stats.states_discovered += 1
        _emit_cic_progress(
            on_progress,
            scope.page.url,
            stats,
            force=True,
            last_emit_at=last_emit_at,
            phase="cic_baseline",
            view_label=(baseline.title or baseline_url)[:80],
        )

        if extract_links_fn and scope.is_main:
            links = extract_links_fn(scope.page, baseline_url)
            result.all_links.update(links)

        frontiers = {0: [baseline.state_key]}
        baseline_ref = result.baseline_elements if scope.is_main else baseline.elements

    start_depth = min(frontiers.keys()) if frontiers else 0

    for depth in range(start_depth, settings.max_interaction_depth):
        parent_keys = frontiers.get(depth, [])
        if not parent_keys:
            break

        child_keys: list[str] = []

        for parent_key in parent_keys:
            if len(result.states) >= settings.max_states_per_url:
                break
            if stats.states_discovered >= settings.max_states_total:
                break
            if (
                not settings.cic_unlimited_interactions
                and interactions_this_url >= settings.max_interactions_per_url
            ):
                break

            parent_state = states_by_key[parent_key]
            state_interactions = interactions_this_state.get(parent_key, 0)
            if (
                not settings.cic_unlimited_interactions
                and state_interactions >= settings.max_interactions_per_state
            ):
                continue

            if depth > 0:
                path = build_replay_path(parent_key, states_by_key)
                if not replay_to_state(
                    scope,
                    baseline_url=baseline_url,
                    target=parent_state,
                    path=path,
                    settings=settings,
                    detect_blockers=detect_blockers,
                ):
                    continue

            seed_elements = parent_state.elements if depth == 0 else (
                diff_elements(baseline_ref, parent_state.elements) or parent_state.elements
            )
            max_candidates = None if settings.cic_unlimited_interactions else settings.max_interactions_per_state
            actions = plan_interactions(
                seed_elements,
                page_url=scope.page.url,
                blocked_patterns=settings.blocked_interaction_patterns,
                already_interacted=interacted,
                parent_state_key=parent_key,
                context_scoped_dedup=context_scoped,
                in_page_only=settings.cic_in_page_only,
                max_candidates=max_candidates,
                safe_form_fill=settings.safe_form_fill,
                rich_interactions=settings.cic_rich_interactions,
                enable_tables=settings.cic_enable_tables,
                enable_date_pickers=settings.cic_enable_date_pickers,
            )

            for action in actions:
                if len(result.states) >= settings.max_states_per_url:
                    break
                if stats.states_discovered >= settings.max_states_total:
                    break
                if (
                    not settings.cic_unlimited_interactions
                    and interactions_this_url >= settings.max_interactions_per_url
                ):
                    break

                current_state_count = interactions_this_state.get(parent_key, 0)
                if (
                    not settings.cic_unlimited_interactions
                    and current_state_count >= settings.max_interactions_per_state
                ):
                    break

                dedup_key = _interaction_dedup_key(
                    action.interaction_key,
                    parent_key,
                    context_scoped=context_scoped,
                )
                if dedup_key in interacted:
                    continue

                safe, _reason = is_safe_to_interact(
                    _action_to_element(action),
                    page_url=scope.page.url,
                    blocked_patterns=settings.blocked_interaction_patterns,
                    allow_form_fill=settings.safe_form_fill,
                )
                if not safe:
                    stats.skipped_interaction_safety += 1
                    continue

                if depth > 0:
                    replay_path = build_replay_path(parent_key, states_by_key)
                    if not replay_to_state(
                        scope,
                        baseline_url=baseline_url,
                        target=parent_state,
                        path=replay_path,
                        settings=settings,
                        detect_blockers=detect_blockers,
                    ):
                        continue
                elif scope.is_main and not is_at_baseline(scope.page.url, baseline_url):
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
                interactions_this_state[parent_key] = interactions_this_state.get(parent_key, 0) + 1
                stats.interactions_executed += 1
                interacted.add(dedup_key)
                result.interaction_events.append(
                    InteractionEventSnapshot(
                        timestamp_ms=(time.monotonic() - session_start) * 1000.0,
                        interaction_key=action.interaction_key,
                        action_type=action.action_type,
                        semantic_selector=action.semantic_selector,
                        text_content=action.text_content,
                        trigger_action=action.model_dump(),
                    )
                )

                navigated_away = navigated_away_from_baseline(post_url, baseline_url)
                if scope.is_main and is_url_discovery(pre_url, post_url, baseline_url):
                    discovered = normalize_discovery_url(post_url)
                    result.discovered_urls.append(
                        DiscoveredUrl(
                            url=discovered,
                            discovered_via="interaction",
                            source_page_url=baseline_url,
                            source_state_key=parent_key,
                            trigger_interaction=action,
                            arrival_replay_path=_arrival_path_for_discovery(
                                parent_key, action, states_by_key
                            ),
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
                    allowed_domains=settings.allowed_domains,
                    include_virtual_forms=include_virtual,
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
                    if scope.is_main:
                        recover_after_interaction(
                            scope.page,
                            baseline_url,
                            page_timeout_ms=settings.page_timeout_ms,
                            navigated_away=navigated_away,
                        )
                    continue

                known_fingerprints.add(new_state.fingerprint or "")
                states_by_key[new_state.state_key] = new_state
                result.states.append(new_state)
                result.transitions.append(
                    StateTransition(
                        from_state_key=parent_key,
                        to_state_key=new_state.state_key,
                        action=action,
                    )
                )
                stats.states_discovered += 1
                child_keys.append(new_state.state_key)
                _emit_cic_progress(
                    on_progress,
                    scope.page.url,
                    stats,
                    force=True,
                    last_emit_at=last_emit_at,
                    phase="new_state",
                    view_label=_view_label_from_action(action),
                )

                if extract_links_fn and scope.is_main:
                    result.all_links.update(extract_links_fn(scope.page, baseline_url))

                if scope.is_main:
                    recover_after_interaction(
                        scope.page,
                        baseline_url,
                        page_timeout_ms=settings.page_timeout_ms,
                        navigated_away=navigated_away,
                    )

        if child_keys:
            frontiers[depth + 1] = child_keys


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
    max_candidates = None if settings.cic_unlimited_interactions else settings.max_interactions_per_state
    actions = plan_interactions(
        elements,
        page_url=page_url,
        blocked_patterns=settings.blocked_interaction_patterns,
        already_interacted=interacted,
        in_page_only=settings.cic_in_page_only,
        max_candidates=max_candidates,
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
