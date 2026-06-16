"""Crawl scope settings (SPEC §15.1, Day 16)."""

from __future__ import annotations

from urllib.parse import urlparse

from pydantic import BaseModel, Field


class CrawlSettings(BaseModel):
    max_depth: int = Field(default=5, ge=0, le=10)
    max_pages: int = Field(default=100, ge=1, le=500)
    allowed_domains: list[str] = Field(default_factory=list)
    excluded_urls: list[str] = Field(default_factory=list)
    page_timeout_ms: int = Field(default=30_000, ge=1000, le=120_000)

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

        return cls(
            max_depth=int(config.get("max_depth", 5)),
            max_pages=int(config.get("max_pages", 100)),
            allowed_domains=[d.lower() for d in (allowed or [])],
            excluded_urls=list(config.get("excluded_urls") or []),
            page_timeout_ms=int(config.get("page_timeout_ms", 30_000)),
        )
