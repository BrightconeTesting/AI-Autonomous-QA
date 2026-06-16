"""Discovery worker orchestration helpers."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from aqa_discovery.crawl_settings import CrawlSettings
from aqa_discovery.crawler import CrawlSession, DEFAULT_PAGE_TIMEOUT_MS
from aqa_discovery.types import CrawlResult, PageSnapshot
from aqa_discovery.url_utils import normalize_crawl_url
from aqa_shared.db.models import Application
from aqa_shared.db.session import get_session_factory


def _build_start_urls(app: Application) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for candidate in [app.base_url, *(app.seed_urls or [])]:
        if not candidate:
            continue
        key = normalize_crawl_url(candidate)
        if key in seen:
            continue
        seen.add(key)
        urls.append(candidate)
    return urls


def crawl_application(
    application_id: str,
    *,
    crawl_overrides: dict | None = None,
    db: Session | None = None,
) -> CrawlResult:
    """Load application config and run a scoped BFS crawl (Day 16)."""
    owns_session = db is None
    session = db or get_session_factory()()
    try:
        app = session.get(Application, uuid.UUID(application_id))
        if app is None:
            raise ValueError(f"Application not found: {application_id}")
        crawl_config = app.crawl_config if isinstance(app.crawl_config, dict) else {}
        settings = CrawlSettings.from_crawl_config(app.base_url, crawl_config, overrides=crawl_overrides)
        start_urls = _build_start_urls(app)
    finally:
        if owns_session:
            session.close()

    with CrawlSession(page_timeout_ms=settings.page_timeout_ms) as crawl:
        return crawl.crawl_bfs(start_urls, settings)


def fetch_application_homepage(
    application_id: str,
    *,
    db: Session | None = None,
) -> PageSnapshot:
    """Fetch only the application base_url (Day 15 compatibility)."""
    result = crawl_application(
        application_id,
        crawl_overrides={"max_depth": 0, "max_pages": 1},
        db=db,
    )
    if not result.pages:
        raise RuntimeError(f"No pages fetched for application {application_id}")
    return result.pages[0]
