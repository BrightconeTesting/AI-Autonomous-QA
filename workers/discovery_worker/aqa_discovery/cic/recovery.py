"""Recovery after CIC interaction branches (Phase 2: modal-aware)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_CLOSE_SELECTORS = (
    "[aria-label='Close' i]",
    "[aria-label='Dismiss' i]",
    "button:has-text('Close')",
    "button:has-text('Cancel')",
    "[role='dialog'] button[aria-label*='close' i]",
)

_DIALOG_SELECTOR = "[role='dialog']:visible, [aria-modal='true']:visible"


def _visible_dialog_count(page) -> int:
    try:
        return page.locator(_DIALOG_SELECTOR).count()
    except Exception:
        return 0


def _wait_dialogs_closed(page, *, timeout_ms: int = 2000) -> None:
    if _visible_dialog_count(page) == 0:
        return
    try:
        page.wait_for_function(
            "() => {"
            "  const dialogs = document.querySelectorAll('[role=dialog], [aria-modal=true]');"
            "  return Array.from(dialogs).every(el => el.hidden || getComputedStyle(el).display === 'none');"
            "}",
            timeout=timeout_ms,
        )
    except Exception:
        pass


def _try_escape_and_close(page) -> None:
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)
    except Exception:
        pass

    for selector in _CLOSE_SELECTORS:
        try:
            loc = page.locator(selector)
            if loc.count() > 0 and loc.first.is_visible():
                loc.first.click(timeout=1500)
                page.wait_for_timeout(150)
                break
        except Exception:
            continue

    _wait_dialogs_closed(page)


def recover_to_baseline(
    page,
    baseline_url: str,
    *,
    page_timeout_ms: int,
    allow_reload: bool = True,
) -> bool:
    """Return to baseline UI. Reload only when the browser left the baseline URL."""
    from aqa_discovery.cic.url_compare import is_at_baseline

    if is_at_baseline(page.url, baseline_url):
        _try_escape_and_close(page)
        return True

    _try_escape_and_close(page)
    if is_at_baseline(page.url, baseline_url):
        return True

    if not allow_reload:
        return False

    try:
        page.goto(baseline_url, timeout=page_timeout_ms, wait_until="domcontentloaded")
    except Exception as exc:
        logger.warning("CIC recovery goto failed", extra={"url": baseline_url, "error": str(exc)})
        return False

    _wait_dialogs_closed(page)
    return is_at_baseline(page.url, baseline_url)


def recover_after_interaction(
    page,
    baseline_url: str,
    *,
    page_timeout_ms: int,
    navigated_away: bool,
) -> bool:
    """Lightweight post-interaction recovery — avoid full reload when still on the same URL."""
    if not navigated_away:
        _try_escape_and_close(page)
        return True
    return recover_to_baseline(page, baseline_url, page_timeout_ms=page_timeout_ms, allow_reload=True)
