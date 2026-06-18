"""URL comparison helpers for CIC discovery and recovery (Phase 2)."""

from __future__ import annotations

from aqa_discovery.url_utils import normalize_crawl_url


def normalize_discovery_url(url: str) -> str:
    """Canonical URL for comparing discoveries and baseline recovery."""
    return normalize_crawl_url(url)


def is_at_baseline(page_url: str, baseline_url: str) -> bool:
    return normalize_discovery_url(page_url) == normalize_discovery_url(baseline_url)


def is_url_discovery(pre_url: str, post_url: str, baseline_url: str) -> bool:
    """True when an interaction revealed a new in-scope route worth enqueueing."""
    if post_url == pre_url:
        return False
    if is_at_baseline(post_url, baseline_url) and is_at_baseline(pre_url, baseline_url):
        return False
    return normalize_discovery_url(post_url) != normalize_discovery_url(pre_url)


def navigated_away_from_baseline(page_url: str, baseline_url: str) -> bool:
    return not is_at_baseline(page_url, baseline_url)
