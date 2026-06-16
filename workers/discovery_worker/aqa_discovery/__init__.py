"""Playwright discovery worker (Day 15+)."""

from aqa_discovery.crawl_settings import CrawlSettings
from aqa_discovery.crawler import CrawlSession, fetch_page
from aqa_discovery.types import CrawlResult, PageSnapshot
from aqa_discovery.url_utils import (
    is_allowed_domain,
    is_excluded_url,
    normalize_crawl_url,
    resolve_link,
)
from aqa_discovery.worker import crawl_application, fetch_application_homepage

__all__ = [
    "CrawlSession",
    "CrawlSettings",
    "CrawlResult",
    "PageSnapshot",
    "crawl_application",
    "fetch_application_homepage",
    "fetch_page",
    "is_allowed_domain",
    "is_excluded_url",
    "normalize_crawl_url",
    "resolve_link",
]
