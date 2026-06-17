"""Crawl scope settings (SPEC §15.1, Day 16–17)."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field


WaitUntil = Literal["domcontentloaded", "load", "networkidle"]


class CrawlSettings(BaseModel):
    max_depth: int = Field(default=5, ge=0, le=10)
    max_pages: int = Field(default=100, ge=1, le=500)
    allowed_domains: list[str] = Field(default_factory=list)
    excluded_urls: list[str] = Field(default_factory=list)
    page_timeout_ms: int = Field(default=30_000, ge=1000, le=120_000)
    respect_robots_txt: bool = True
    max_scroll_iterations: int = Field(default=10, ge=0, le=50)
    wait_until: WaitUntil = "domcontentloaded"
    wait_for_selector: str | None = None

    @classmethod
    def from_crawl_config(
        cls,
        base_url: str,
        crawl_config: dict | None,
        *,
        overrides: dict | None = None,
    ) -> CrawlSettings:
        config = dict(crawl_config or {})
        if overrides:
            config.update(overrides)

        hostname = urlparse(base_url).hostname
        allowed = config.get("allowed_domains")
        if not allowed and hostname:
            allowed = [hostname.lower()]

        wait_until = config.get("wait_until", config.get("spa_wait_until", "domcontentloaded"))
        if wait_until not in ("domcontentloaded", "load", "networkidle"):
            wait_until = "domcontentloaded"

        return cls(
            max_depth=int(config.get("max_depth", 5)),
            max_pages=int(config.get("max_pages", 100)),
            allowed_domains=[d.lower() for d in (allowed or [])],
            excluded_urls=list(config.get("excluded_urls") or []),
            page_timeout_ms=int(config.get("page_timeout_ms", 30_000)),
            respect_robots_txt=bool(config.get("respect_robots_txt", True)),
            max_scroll_iterations=int(config.get("max_scroll_iterations", 10)),
            wait_until=wait_until,
            wait_for_selector=config.get("wait_for_selector"),
        )
