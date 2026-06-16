#!/usr/bin/env python3
"""Verify DiscoveryWorker Playwright fetch + BFS crawl — Days 15–16."""

from __future__ import annotations

import sys

from aqa_discovery.crawl_settings import CrawlSettings
from aqa_discovery.crawler import CrawlSession, fetch_page
from aqa_discovery.url_utils import is_allowed_domain, is_excluded_url, normalize_crawl_url


def _verify_url_utils() -> bool:
    assert normalize_crawl_url("https://Example.com/path/") == "https://example.com/path"
    assert normalize_crawl_url("https://example.com/#/login") == "https://example.com/#/login"
    assert is_allowed_domain("https://example.com/a", {"example.com"}) is True
    assert is_allowed_domain("https://other.com/a", {"example.com"}) is False
    assert is_excluded_url("https://example.com/logout", ["**/logout**"]) is True
    assert is_excluded_url("https://example.com/about", ["**/logout**"]) is False
    print("OK url_utils: normalize, allowed_domains, excluded_urls")
    return True


def _verify_single_fetch() -> bool:
    try:
        with CrawlSession() as session:
            snapshot = session.fetch_page("https://example.com")
    except Exception as exc:
        hint = "Run `pnpm playwright:install` if browsers are missing."
        print(f"FAIL CrawlSession fetch: {exc}", file=sys.stderr)
        print(f"Hint: {hint}", file=sys.stderr)
        return False

    if snapshot.status != 200 or not snapshot.title or snapshot.html_length <= 0:
        print(f"FAIL single fetch snapshot: {snapshot}", file=sys.stderr)
        return False
    print(
        f"OK CrawlSession fetch_page: url={snapshot.url} title={snapshot.title!r} "
        f"html_length={snapshot.html_length}"
    )

    standalone = fetch_page("https://example.com")
    if standalone.status != 200 or standalone.html_length <= 0:
        print("FAIL standalone fetch_page helper", file=sys.stderr)
        return False
    print(f"OK fetch_page helper: html_length={standalone.html_length}")
    return True


def _verify_bfs_crawl() -> bool:
    settings = CrawlSettings(
        max_depth=2,
        max_pages=5,
        allowed_domains=["example.com", "www.example.com"],
        excluded_urls=["**/iana.org/**"],
        page_timeout_ms=30_000,
    )
    try:
        with CrawlSession(page_timeout_ms=settings.page_timeout_ms) as session:
            result = session.crawl_bfs(["https://example.com"], settings)
    except Exception as exc:
        print(f"FAIL BFS crawl: {exc}", file=sys.stderr)
        return False

    if not result.pages:
        print("FAIL BFS crawl returned no pages", file=sys.stderr)
        return False
    if len(result.pages) > settings.max_pages:
        print(f"FAIL BFS exceeded max_pages: {len(result.pages)}", file=sys.stderr)
        return False
    if result.stats.pages_crawled != len(result.pages):
        print("FAIL BFS stats.pages_crawled mismatch", file=sys.stderr)
        return False

    for page in result.pages:
        host = page.url.split("/")[2].lower()
        if not host.endswith("example.com"):
            print(f"FAIL off-domain page crawled: {page.url}", file=sys.stderr)
            return False

    print(
        f"OK BFS crawl: pages={len(result.pages)} "
        f"skipped_off_domain={result.stats.skipped_off_domain} "
        f"skipped_excluded={result.stats.skipped_excluded}"
    )
    return True


def main() -> int:
    print("verify:discovery")
    if not _verify_url_utils():
        return 1
    if not _verify_single_fetch():
        return 1
    if not _verify_bfs_crawl():
        return 1
    print("verify:discovery OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
