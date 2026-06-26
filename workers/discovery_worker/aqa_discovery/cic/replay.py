"""Replay paths to reach a discovered UI state (state-based CIC exploration)."""

from __future__ import annotations

import logging
from collections.abc import Callable

from aqa_discovery.cic.executor import execute_interaction
from aqa_discovery.cic.fingerprint import compute_state_fingerprint
from aqa_discovery.cic.recovery import recover_to_baseline
from aqa_discovery.cic.url_compare import is_at_baseline
from aqa_discovery.crawl_settings import CrawlSettings
from aqa_discovery.extractors import detect_dialog_titles
from aqa_discovery.page_capture import capture_interactive_data
from aqa_discovery.types import InteractionAction, UIStateSnapshot

logger = logging.getLogger(__name__)


def build_replay_path(
    target_state_key: str,
    states_by_key: dict[str, UIStateSnapshot],
) -> list[InteractionAction]:
    """Walk parent_state_key chain from target back to baseline; return actions in order."""
    path: list[InteractionAction] = []
    current = states_by_key.get(target_state_key)
    if current is None:
        return []

    while current and current.parent_state_key:
        trigger = current.trigger_interaction
        if trigger is not None:
            path.append(trigger)
        current = states_by_key.get(current.parent_state_key or "")
        if current is None:
            break

    path.reverse()
    return path


def replay_to_state(
    scope,
    *,
    baseline_url: str,
    target: UIStateSnapshot,
    path: list[InteractionAction],
    settings: CrawlSettings,
    detect_blockers: Callable | None = None,
) -> bool:
    """Navigate to baseline and replay actions until the target UI state is reached."""
    if scope.is_main:
        if not is_at_baseline(scope.page.url, baseline_url):
            if not recover_to_baseline(scope.page, baseline_url, page_timeout_ms=settings.page_timeout_ms):
                return False
        else:
            from aqa_discovery.cic.recovery import _try_escape_and_close

            _try_escape_and_close(scope.page)

    for action in path:
        try:
            if detect_blockers and scope.is_main:
                detect_blockers(scope.page)
            execute_interaction(scope, action, settings)
        except Exception as exc:
            logger.debug(
                "CIC replay step failed",
                extra={"key": action.interaction_key, "error": str(exc)},
            )
            return False

    if not settings.cic_replay_verify_fingerprint or not target.fingerprint:
        return True

    frame_scope = None if scope.is_main else scope
    elements, _forms = capture_interactive_data(
        scope.page,
        frame_scope,
        page_url=scope.page.url,
        allowed_domains=settings.allowed_domains,
        include_virtual_forms=settings.cic_virtual_forms,
    )
    dialogs = detect_dialog_titles(scope.page)
    dialog_titles = list(dialogs)
    if scope.frame_name and scope.frame_name != "main":
        dialog_titles.append(f"frame:{scope.frame_name}")

    actual = compute_state_fingerprint(
        url=scope.page.url,
        title=scope.page.title(),
        elements=elements,
        dialog_titles=dialog_titles,
    )
    if actual != target.fingerprint:
        logger.debug(
            "CIC replay fingerprint mismatch",
            extra={"expected": target.fingerprint, "actual": actual, "state_key": target.state_key},
        )
        return False
    return True
