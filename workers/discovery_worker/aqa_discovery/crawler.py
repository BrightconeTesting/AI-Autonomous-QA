"""Playwright crawl session, single-page fetch, and BFS crawl (Day 15–16)."""

from __future__ import annotations

import logging
from collections import deque

from aqa_discovery.crawl_settings import CrawlSettings
from aqa_discovery.types import CrawlResult, CrawlStats, PageSnapshot
from aqa_discovery.url_utils import (
    is_allowed_domain,
    is_excluded_url,
    is_http_url,
    normalize_crawl_url,
    resolve_link,
)

logger = logging.getLogger(__name__)

DEFAULT_PAGE_TIMEOUT_MS = 30_000


class CrawlSession:
    """Headless Chromium session — opens browser on enter, closes on exit."""

    def __init__(self, *, page_timeout_ms: int = DEFAULT_PAGE_TIMEOUT_MS, headless: bool = True) -> None:
        self.page_timeout_ms = page_timeout_ms
        self.headless = headless
        self._playwright = None
        self._browser = None

    def __enter__(self) -> CrawlSession:
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        logger.info("DiscoveryWorker browser started", extra={"headless": self.headless})
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None
        logger.info("DiscoveryWorker browser closed")

    def _visit_page(self, url: str, *, depth: int = 0) -> tuple[PageSnapshot, list[str]]:
        if self._browser is None:
            raise RuntimeError("CrawlSession is not active — use as a context manager")

        page = self._browser.new_page()
        try:
            response = page.goto(
                url,
                timeout=self.page_timeout_ms,
                wait_until="domcontentloaded",
            )
            status = response.status if response is not None else 0
            html = page.content()
            snapshot = PageSnapshot(
                url=page.url,
                title=page.title(),
                status=status,
                html_length=len(html),
                depth=depth,
            )
            raw_hrefs: list[str] = page.eval_on_selector_all(
                "a[href]",
                "elements => elements.map(element => element.href)",
            )
            links: list[str] = []
            for href in raw_hrefs:
                link = resolve_link(snapshot.url, href)
                if link is not None:
                    links.append(link)
            logger.info(
                "DiscoveryWorker page fetched",
                extra={
                    "url": snapshot.url,
                    "status": snapshot.status,
                    "title": snapshot.title,
                    "htmlLength": snapshot.html_length,
                    "depth": depth,
                    "linksFound": len(links),
                },
            )
            return snapshot, links
        finally:
            page.close()

    def fetch_page(self, url: str, *, depth: int = 0) -> PageSnapshot:
        snapshot, _links = self._visit_page(url, depth=depth)
        return snapshot

    def crawl_bfs(self, start_urls: list[str], settings: CrawlSettings) -> CrawlResult:
        """Breadth-first crawl with scope limits (SPEC §15.1, Day 16)."""
        allowed = set(settings.allowed_domains)
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque()
        pages: list[PageSnapshot] = []
        stats = CrawlStats(max_pages=settings.max_pages, max_depth=settings.max_depth)

        for start in start_urls:
            if not is_http_url(start):
                continue
            key = normalize_crawl_url(start)
            if key not in visited:
                visited.add(key)
                queue.append((start, 0))

        while queue and len(pages) < settings.max_pages:
            url, depth = queue.popleft()
            try:
                snapshot, links = self._visit_page(url, depth=depth)
            except Exception as exc:
                logger.warning(
                    "DiscoveryWorker page fetch failed",
                    extra={"url": url, "depth": depth, "error": str(exc)},
                )
                continue

            pages.append(snapshot)

            if depth >= settings.max_depth:
                continue

            for link in links:
                if len(pages) + len(queue) >= settings.max_pages:
                    break
                if not is_allowed_domain(link, allowed):
                    stats.skipped_off_domain += 1
                    continue
                if is_excluded_url(link, settings.excluded_urls):
                    stats.skipped_excluded += 1
                    continue
                key = normalize_crawl_url(link)
                if key in visited:
                    stats.skipped_duplicate += 1
                    continue
                visited.add(key)
                queue.append((link, depth + 1))

        stats.pages_crawled = len(pages)
        logger.info(
            "DiscoveryWorker BFS crawl finished",
            extra={
                "pagesCrawled": stats.pages_crawled,
                "skippedOffDomain": stats.skipped_off_domain,
                "skippedExcluded": stats.skipped_excluded,
                "skippedDuplicate": stats.skipped_duplicate,
            },
        )
        return CrawlResult(pages=pages, stats=stats)


def fetch_page(url: str, *, page_timeout_ms: int = DEFAULT_PAGE_TIMEOUT_MS, headless: bool = True) -> PageSnapshot:
    """Fetch a single page in a short-lived browser session."""
    with CrawlSession(page_timeout_ms=page_timeout_ms, headless=headless) as session:
        return session.fetch_page(url)
