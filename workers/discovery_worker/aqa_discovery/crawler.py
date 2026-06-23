"""Playwright crawl session, single-page fetch, and BFS crawl (Day 15–17)."""

from __future__ import annotations

import logging
import time
import uuid
from collections import deque
from collections.abc import Callable

from aqa_discovery.crawl_settings import CrawlSettings
from aqa_discovery.page_capture import capture_interactive_data
from aqa_discovery.extractors import save_page_screenshot
from aqa_discovery.persist import screenshot_path_for_page
from aqa_discovery.robots import RobotsChecker
from aqa_discovery.safety import is_safety_excluded_link, is_safety_excluded_url
from aqa_discovery.spa_views import expand_spa_views, is_virtual_view_url
from aqa_discovery.spa_routes import collect_spa_route_events, install_spa_route_listener
from aqa_discovery.types import CrawlHaltError, CrawlResult, CrawlStats, PageSnapshot
from aqa_discovery.url_utils import (
    is_allowed_domain,
    is_excluded_url,
    is_http_url,
    normalize_crawl_url,
    resolve_link,
)

logger = logging.getLogger(__name__)

DEFAULT_PAGE_TIMEOUT_MS = 30_000

_CAPTCHA_SELECTORS = (
    ".g-recaptcha",
    "#recaptcha",
    ".h-captcha",
    "iframe[src*='recaptcha']",
    "iframe[src*='hcaptcha']",
    "[data-sitekey]",
    "[data-hcaptcha-sitekey]",
)

_MFA_SELECTORS = (
    "input[autocomplete='one-time-code']",
    "input[name*='otp' i]",
    "input[name*='mfa' i]",
    "input[name*='totp' i]",
    "input[id*='otp' i]",
    "input[id*='mfa' i]",
)

_MFA_TEXT_MARKERS = (
    "verification code",
    "authenticator app",
    "two-factor",
    "two factor",
    "multi-factor",
    "enter the code",
    "one-time password",
)

_LINK_EXTRACTION_JS = """
elements => elements.map(element => ({
  href: element.href,
  rawHref: element.getAttribute('href') || '',
  text: (element.textContent || '').trim(),
}))
"""


class CrawlSession:
    """Headless Chromium session — opens browser on enter, closes on exit."""

    def __init__(
        self,
        *,
        page_timeout_ms: int = DEFAULT_PAGE_TIMEOUT_MS,
        headless: bool = True,
        browser_channel: str | None = None,
        user_agent: str | None = None,
        locale: str | None = None,
        viewport_width: int | None = None,
        viewport_height: int | None = None,
        app_id: uuid.UUID | None = None,
        capture_artifacts: bool = False,
    ) -> None:
        self.page_timeout_ms = page_timeout_ms
        self.headless = headless
        self.browser_channel = browser_channel
        self.user_agent = user_agent
        self.locale = locale
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.app_id = app_id
        self.capture_artifacts = capture_artifacts
        self._playwright = None
        self._browser = None
        self._context = None

    def __enter__(self) -> CrawlSession:
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        launch_kwargs: dict = {"headless": self.headless}
        if self.browser_channel:
            launch_kwargs["channel"] = self.browser_channel
        self._browser = self._playwright.chromium.launch(**launch_kwargs)
        context_kwargs: dict = {}
        if self.user_agent:
            context_kwargs["user_agent"] = self.user_agent
        if self.locale:
            context_kwargs["locale"] = self.locale
        if self.viewport_width and self.viewport_height:
            context_kwargs["viewport"] = {
                "width": self.viewport_width,
                "height": self.viewport_height,
            }
        self._context = self._browser.new_context(**context_kwargs)
        logger.info(
            "DiscoveryWorker browser started",
            extra={
                "headless": self.headless,
                "browserChannel": self.browser_channel,
                "hasCustomUserAgent": bool(self.user_agent),
            },
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._context is not None:
            self._context.close()
            self._context = None
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None
        logger.info("DiscoveryWorker browser closed")

    def authenticate(
        self,
        *,
        auth_config: dict,
        base_url: str,
        audit: Callable | None = None,
    ) -> bool:
        """Run form login or cookie injection before crawl (Day 18)."""
        if self._context is None:
            raise RuntimeError("CrawlSession is not active — use as a context manager")

        from aqa_discovery.auth import authenticate_browser

        return authenticate_browser(
            self._context,
            auth_config=auth_config,
            base_url=base_url,
            page_timeout_ms=self.page_timeout_ms,
            audit=audit,
            detect_blockers=self._detect_captcha_or_mfa,
        )

    def _detect_captcha_or_mfa(self, page) -> None:
        for selector in _CAPTCHA_SELECTORS:
            if page.locator(selector).count() > 0:
                raise CrawlHaltError(
                    "CAPTCHA detected on page. Provide pre-authenticated session cookies via "
                    "auth_config.cookies or disable CAPTCHA in the test environment.",
                    url=page.url,
                    reason="captcha",
                )

        for selector in _MFA_SELECTORS:
            if page.locator(selector).count() > 0:
                raise CrawlHaltError(
                    "MFA prompt detected. Use test credentials with MFA disabled or inject "
                    "a session cookie via auth_config.cookies.",
                    url=page.url,
                    reason="mfa",
                )

        body_text = page.locator("body").inner_text(timeout=2_000).lower()
        for marker in _MFA_TEXT_MARKERS:
            if marker in body_text:
                raise CrawlHaltError(
                    "MFA prompt detected. Use test credentials with MFA disabled or inject "
                    "a session cookie via auth_config.cookies.",
                    url=page.url,
                    reason="mfa",
                )

    def _perform_infinite_scroll(self, page, *, max_iterations: int) -> None:
        if max_iterations <= 0:
            return

        stale_rounds = 0
        previous_link_count = page.locator("a[href]").count()
        for _ in range(max_iterations):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(500)
            link_count = page.locator("a[href]").count()
            if link_count <= previous_link_count:
                stale_rounds += 1
                if stale_rounds >= 2:
                    break
            else:
                stale_rounds = 0
            previous_link_count = link_count

    def _extract_links(self, page, page_url: str) -> list[str]:
        raw_links: list[dict[str, str]] = page.eval_on_selector_all("a[href]", _LINK_EXTRACTION_JS)
        links: list[str] = []
        seen: set[str] = set()

        for item in raw_links:
            href = item.get("href") or ""
            raw_href = item.get("rawHref") or ""
            text = item.get("text") or ""

            candidates: list[str] = []
            resolved = resolve_link(page_url, href)
            if resolved is not None:
                candidates.append(resolved)
            if raw_href.startswith("#/") or raw_href.startswith("#!/"):
                hash_resolved = resolve_link(page_url, raw_href)
                if hash_resolved is not None:
                    candidates.append(hash_resolved)

            for candidate in candidates:
                if is_safety_excluded_link(href=candidate, link_text=text):
                    continue
                key = normalize_crawl_url(candidate)
                if key in seen:
                    continue
                seen.add(key)
                links.append(candidate)

        return links

    def _visit_page(
        self,
        url: str,
        *,
        depth: int,
        settings: CrawlSettings,
        stats: CrawlStats | None = None,
        on_cic_progress: Callable[[str, CrawlStats, dict], None] | None = None,
    ) -> tuple[PageSnapshot, list[str]]:
        if self._context is None:
            raise RuntimeError("CrawlSession is not active — use as a context manager")

        page = self._context.new_page()
        crawl_stats = stats or CrawlStats()
        page_session_start = time.monotonic()
        install_spa_route_listener(page)
        network_capture = None
        if settings.capture_network:
            from aqa_discovery.network_capture import NetworkCapture

            network_capture = NetworkCapture(
                page_url=url,
                allowed_domains=settings.allowed_domains,
                excluded_analytics_domains=settings.excluded_analytics_domains,
            )
            network_capture.attach(page)
        try:
            response = page.goto(
                url,
                timeout=self.page_timeout_ms,
                wait_until=settings.wait_until,
            )
            if settings.wait_for_selector:
                page.wait_for_selector(
                    settings.wait_for_selector,
                    timeout=self.page_timeout_ms,
                )

            self._detect_captcha_or_mfa(page)
            self._perform_infinite_scroll(page, max_iterations=settings.max_scroll_iterations)

            status = response.status if response is not None else 0
            baseline_url = page.url
            if on_cic_progress is not None:
                on_cic_progress(baseline_url, crawl_stats, {"phase": "page_loaded"})

            if settings.enable_cic:
                from aqa_discovery.cic.session import run_cic_session

                cic_result = run_cic_session(
                    page,
                    baseline_url=baseline_url,
                    status=status,
                    settings=settings,
                    stats=crawl_stats,
                    app_id=self.app_id,
                    capture_artifacts=self.capture_artifacts,
                    extract_links_fn=lambda p, u: self._extract_links(p, u),
                    detect_blockers=self._detect_captcha_or_mfa,
                    on_progress=on_cic_progress,
                    session_start=page_session_start,
                )
                baseline_state = cic_result.states[0] if cic_result.states else None
                if baseline_state:
                    elements = baseline_state.elements
                    forms = baseline_state.forms
                else:
                    elements, forms = capture_interactive_data(
                        page,
                        page_url=baseline_url,
                        allowed_domains=settings.allowed_domains,
                    )
                screenshot_path: str | None = None
                if self.capture_artifacts and self.app_id is not None:
                    dest = screenshot_path_for_page(app_id=self.app_id, url=baseline_url)
                    if baseline_state and baseline_state.screenshot_path:
                        screenshot_path = baseline_state.screenshot_path
                    else:
                        save_page_screenshot(page, dest)
                        screenshot_path = str(dest)

                html_len = baseline_state.html_length if baseline_state else len(page.content())
                page_api_endpoints = network_capture.collect() if network_capture else []
                spa_events = collect_spa_route_events(page, source_page_url=baseline_url)
                snapshot = PageSnapshot(
                    url=baseline_url,
                    title=page.title(),
                    status=status,
                    html_length=html_len,
                    depth=depth,
                    elements=elements,
                    forms=forms,
                    api_endpoints=page_api_endpoints,
                    screenshot_path=screenshot_path,
                    states=cic_result.states,
                    transitions=cic_result.transitions,
                    discovered_urls=cic_result.discovered_urls,
                    har_entries=network_capture.har_entries() if network_capture and settings.capture_har else [],
                    interaction_events=cic_result.interaction_events,
                    network_events=network_capture.network_events() if network_capture else [],
                    spa_route_events=spa_events,
                )
                links = list(cic_result.all_links)
                if not links:
                    links = self._extract_links(page, baseline_url)
                logger.info(
                    "DiscoveryWorker CIC page fetched",
                    extra={
                        "url": snapshot.url,
                        "statesFound": len(cic_result.states),
                        "transitionsFound": len(cic_result.transitions),
                        "discoveredUrls": len(cic_result.discovered_urls),
                        "linksFound": len(links),
                        "elementsFound": len(elements),
                        "interactionsExecuted": crawl_stats.interactions_executed,
                    },
                )
                return snapshot, links

            html = page.content()
            elements, forms = capture_interactive_data(
                page,
                page_url=page.url,
                allowed_domains=settings.allowed_domains,
            )
            screenshot_path = None
            if self.capture_artifacts and self.app_id is not None:
                dest = screenshot_path_for_page(app_id=self.app_id, url=page.url)
                save_page_screenshot(page, dest)
                screenshot_path = str(dest)

            snapshot = PageSnapshot(
                url=page.url,
                title=page.title(),
                status=status,
                html_length=len(html),
                depth=depth,
                elements=elements,
                forms=forms,
                api_endpoints=network_capture.collect() if network_capture else [],
                screenshot_path=screenshot_path,
                har_entries=network_capture.har_entries() if network_capture and settings.capture_har else [],
                spa_route_events=collect_spa_route_events(page, source_page_url=page.url),
            )
            links = self._extract_links(page, snapshot.url)
            logger.info(
                "DiscoveryWorker page fetched",
                extra={
                    "url": snapshot.url,
                    "status": snapshot.status,
                    "title": snapshot.title,
                    "htmlLength": snapshot.html_length,
                    "depth": depth,
                    "linksFound": len(links),
                    "elementsFound": len(elements),
                    "waitUntil": settings.wait_until,
                },
            )
            return snapshot, links
        finally:
            if network_capture is not None:
                network_capture.detach(page)
            page.close()

    def fetch_page(
        self,
        url: str,
        *,
        depth: int = 0,
        settings: CrawlSettings | None = None,
    ) -> PageSnapshot:
        crawl_settings = settings or CrawlSettings()
        snapshot, _links = self._visit_page(url, depth=depth, settings=crawl_settings)
        return snapshot

    def _should_enqueue(
        self,
        link: str,
        *,
        settings: CrawlSettings,
        allowed: set[str],
        robots: RobotsChecker,
        visited: set[str],
        stats: CrawlStats,
    ) -> bool:
        if is_virtual_view_url(link):
            stats.skipped_excluded += 1
            return False
        if not is_allowed_domain(link, allowed):
            stats.skipped_off_domain += 1
            return False
        if is_safety_excluded_url(link):
            stats.skipped_safety += 1
            return False
        if is_excluded_url(link, settings.excluded_urls):
            stats.skipped_excluded += 1
            return False
        if not robots.is_allowed(link):
            stats.skipped_robots += 1
            return False
        key = normalize_crawl_url(link)
        if key in visited:
            stats.skipped_duplicate += 1
            return False
        return True

    def crawl_bfs(
        self,
        start_urls: list[str],
        settings: CrawlSettings,
        *,
        on_progress: Callable[[PageSnapshot, CrawlStats], None] | None = None,
        on_cic_progress: Callable[[str, CrawlStats, dict], None] | None = None,
    ) -> CrawlResult:
        """Breadth-first crawl with scope limits (SPEC §15.1–15.6, Day 16–17)."""
        allowed = set(settings.allowed_domains)
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque()
        pages: list[PageSnapshot] = []
        stats = CrawlStats(max_pages=settings.max_pages, max_depth=settings.max_depth)
        robots = RobotsChecker(
            start_urls[0] if start_urls else "https://example.com",
            enabled=settings.respect_robots_txt,
        )

        for start in start_urls:
            if not is_http_url(start):
                continue
            key = normalize_crawl_url(start)
            if key in visited:
                continue
            if is_safety_excluded_url(start):
                stats.skipped_safety += 1
                continue
            if not robots.is_allowed(start):
                stats.skipped_robots += 1
                continue
            visited.add(key)
            queue.append((start, 0))

        while queue and len(pages) < settings.max_pages:
            url, depth = queue.popleft()
            if is_virtual_view_url(url):
                continue
            try:
                snapshot, links = self._visit_page(
                    url,
                    depth=depth,
                    settings=settings,
                    stats=stats,
                    on_cic_progress=on_cic_progress,
                )
            except CrawlHaltError as exc:
                stats.pages_crawled = len(pages)
                logger.warning(
                    "DiscoveryWorker crawl halted",
                    extra={"url": exc.url or url, "reason": exc.reason, "message": exc.message},
                )
                return self._build_crawl_result(
                    pages,
                    stats,
                    settings,
                    base_url=start_urls[0] if start_urls else "",
                    allowed=allowed,
                    halted=True,
                    halt_reason=exc.message,
                    halt_url=exc.url or url,
                )
            except Exception as exc:
                logger.warning(
                    "DiscoveryWorker page fetch failed",
                    extra={"url": url, "depth": depth, "error": str(exc)},
                )
                continue

            for page_snapshot in expand_spa_views(snapshot):
                pages.append(page_snapshot)
                stats.pages_crawled = len(pages)
                if on_progress is not None:
                    on_progress(page_snapshot, stats)

            if depth >= settings.max_depth:
                all_enqueue = [item.url for item in snapshot.discovered_urls]
            else:
                all_enqueue = list(links)
            for item in snapshot.discovered_urls:
                if item.url not in all_enqueue:
                    all_enqueue.append(item.url)

            if not all_enqueue:
                continue

            for link in all_enqueue:
                if len(pages) + len(queue) >= settings.max_pages:
                    break
                if not self._should_enqueue(
                    link,
                    settings=settings,
                    allowed=allowed,
                    robots=robots,
                    visited=visited,
                    stats=stats,
                ):
                    continue
                visited.add(normalize_crawl_url(link))
                queue.append((link, depth + 1))

        stats.pages_crawled = len(pages)
        logger.info(
            "DiscoveryWorker BFS crawl finished",
            extra={
                "pagesCrawled": stats.pages_crawled,
                "statesDiscovered": stats.states_discovered,
                "interactionsExecuted": stats.interactions_executed,
                "skippedOffDomain": stats.skipped_off_domain,
                "skippedExcluded": stats.skipped_excluded,
                "skippedSafety": stats.skipped_safety,
                "skippedInteractionSafety": stats.skipped_interaction_safety,
                "skippedRobots": stats.skipped_robots,
                "skippedDuplicate": stats.skipped_duplicate,
                "apiEndpoints": len(self._merge_crawl_api_endpoints(pages, settings, start_urls[0] if start_urls else "", allowed)),
            },
        )
        return self._build_crawl_result(pages, stats, settings, base_url=start_urls[0] if start_urls else "", allowed=allowed)

    def _merge_crawl_api_endpoints(
        self,
        pages: list[PageSnapshot],
        settings: CrawlSettings,
        base_url: str,
        allowed: set[str],
    ) -> list:
        from aqa_discovery.network_capture import merge_api_endpoints

        page_endpoints = [endpoint for page in pages for endpoint in page.api_endpoints]
        openapi_endpoints = []
        if settings.openapi_url:
            try:
                from aqa_discovery.openapi_import import fetch_openapi_endpoints

                openapi_endpoints = fetch_openapi_endpoints(
                    settings.openapi_url,
                    base_url=base_url,
                    allowed_domains=list(allowed),
                )
            except Exception as exc:
                logger.warning("DiscoveryWorker OpenAPI import skipped: %s", exc)
        return merge_api_endpoints(page_endpoints, openapi_endpoints)

    def _build_crawl_result(
        self,
        pages: list[PageSnapshot],
        stats: CrawlStats,
        settings: CrawlSettings,
        *,
        base_url: str,
        allowed: set[str],
        halted: bool = False,
        halt_reason: str | None = None,
        halt_url: str | None = None,
    ) -> CrawlResult:
        har_entries = [entry for page in pages for entry in page.har_entries]
        from aqa_discovery.spa_routes import aggregate_spa_route_events

        return CrawlResult(
            pages=pages,
            api_endpoints=self._merge_crawl_api_endpoints(pages, settings, base_url, allowed),
            har_entries=har_entries if settings.capture_har else [],
            stats=stats,
            halted=halted,
            halt_reason=halt_reason,
            halt_url=halt_url,
            spa_route_events=aggregate_spa_route_events(pages),
        )


def fetch_page(url: str, *, page_timeout_ms: int = DEFAULT_PAGE_TIMEOUT_MS, headless: bool = True) -> PageSnapshot:
    """Fetch a single page in a short-lived browser session."""
    with CrawlSession(page_timeout_ms=page_timeout_ms, headless=headless) as session:
        return session.fetch_page(url)
