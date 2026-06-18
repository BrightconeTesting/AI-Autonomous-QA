"""Playwright interaction execution (CIC Phase 1–3)."""

from __future__ import annotations

import logging
import re

from aqa_discovery.interaction_safety import canned_fill_value
from aqa_discovery.crawl_settings import CrawlSettings
from aqa_discovery.types import InteractionAction

logger = logging.getLogger(__name__)

_PLACEHOLDER_OPTION = re.compile(r"^(select|choose|--|please select).*$", re.IGNORECASE)


def _scope_locator(scope, action: InteractionAction):
    if action.xpath_fallback:
        return scope.locator(f"xpath={action.xpath_fallback}")
    if action.semantic_selector and action.semantic_selector.startswith("getByRole"):
        if action.role and action.text_content:
            return scope.get_by_role(action.role, name=action.text_content[:80])
    if action.semantic_selector and action.semantic_selector.startswith("getByLabel"):
        label = action.text_content or action.value
        if label:
            return scope.get_by_label(label[:80])
    if action.text_content:
        return scope.get_by_text(action.text_content[:80], exact=False)
    raise ValueError(f"No locator for interaction {action.interaction_key}")


def wait_for_ui_update(scope, settings: CrawlSettings) -> None:
    strategy = settings.interaction_wait_strategy
    wait_ms = settings.interaction_wait_ms

    if strategy == "network_idle":
        try:
            scope.page.wait_for_load_state("networkidle", timeout=min(wait_ms, 5000))
        except Exception:
            scope.page.wait_for_timeout(wait_ms)
    elif strategy == "dom_stable":
        _wait_dom_stable(scope, wait_ms=wait_ms, max_rounds=settings.cic_dom_stable_rounds)
    else:
        scope.page.wait_for_timeout(wait_ms)


def _wait_dom_stable(scope, *, wait_ms: int, max_rounds: int = 4) -> None:
    stable_count = 0
    previous = -1
    poll_ms = max(80, wait_ms // max_rounds)
    selector = (
        "a[href], button, input:not([type='hidden']), select, textarea, "
        "[role='button'], [role='tab'], [role='menuitem'], [role='option'], summary"
    )
    for _ in range(max_rounds):
        count = scope.locator(selector).count()
        if count == previous:
            stable_count += 1
            if stable_count >= 2:
                return
        else:
            stable_count = 0
        previous = count
        scope.page.wait_for_timeout(poll_ms)


def execute_click(scope, action: InteractionAction, settings: CrawlSettings) -> str:
    locator = _scope_locator(scope, action)
    timeout = min(settings.page_timeout_ms, 10_000)
    locator.first.scroll_into_view_if_needed(timeout=timeout)
    locator.first.click(timeout=timeout)
    wait_for_ui_update(scope, settings)
    return scope.page.url


def execute_hover(scope, action: InteractionAction, settings: CrawlSettings) -> str:
    locator = _scope_locator(scope, action)
    timeout = min(settings.page_timeout_ms, 10_000)
    locator.first.scroll_into_view_if_needed(timeout=timeout)
    locator.first.hover(timeout=timeout)
    wait_for_ui_update(scope, settings)
    return scope.page.url


def execute_fill(scope, action: InteractionAction, settings: CrawlSettings) -> str:
    locator = _scope_locator(scope, action)
    timeout = min(settings.page_timeout_ms, 10_000)
    fill_value = action.value or canned_fill_value({})
    locator.first.scroll_into_view_if_needed(timeout=timeout)
    locator.first.fill(fill_value, timeout=timeout)
    wait_for_ui_update(scope, settings)
    return scope.page.url


def _first_safe_option_index(scope, select_locator) -> int | None:
    options = select_locator.locator("option")
    count = options.count()
    for index in range(count):
        try:
            text = (options.nth(index).inner_text() or "").strip()
            value = (options.nth(index).get_attribute("value") or "").strip()
        except Exception:
            continue
        if not text and not value:
            continue
        if _PLACEHOLDER_OPTION.match(text):
            continue
        if value in ("", "0") and not text:
            continue
        return index
    return None


def execute_select(scope, action: InteractionAction, settings: CrawlSettings) -> str:
    locator = _scope_locator(scope, action)
    timeout = min(settings.page_timeout_ms, 10_000)
    locator.first.scroll_into_view_if_needed(timeout=timeout)
    option_index = _first_safe_option_index(scope, locator.first)
    if option_index is None:
        raise ValueError("no safe select option")
    locator.first.select_option(index=option_index, timeout=timeout)
    wait_for_ui_update(scope, settings)
    return scope.page.url


def execute_interaction(scope, action: InteractionAction, settings: CrawlSettings) -> str:
    """Dispatch interaction by action_type."""
    if action.action_type == "select":
        return execute_select(scope, action, settings)
    if action.action_type == "hover":
        return execute_hover(scope, action, settings)
    if action.action_type == "fill":
        return execute_fill(scope, action, settings)
    return execute_click(scope, action, settings)
