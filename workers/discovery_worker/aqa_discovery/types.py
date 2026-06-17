"""Discovery worker data types."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ElementSnapshot(BaseModel):
    tag_name: str
    role: str | None = None
    text_content: str | None = None
    semantic_selector: str | None = None
    xpath_fallback: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class PageSnapshot(BaseModel):
    url: str
    title: str
    status: int
    html_length: int = Field(ge=0)
    depth: int = Field(default=0, ge=0)
    elements: list[ElementSnapshot] = Field(default_factory=list)
    screenshot_path: str | None = None


class CrawlStats(BaseModel):
    pages_crawled: int = 0
    skipped_off_domain: int = 0
    skipped_excluded: int = 0
    skipped_duplicate: int = 0
    skipped_safety: int = 0
    skipped_robots: int = 0
    max_pages: int = 0
    max_depth: int = 0


class CrawlResult(BaseModel):
    pages: list[PageSnapshot] = Field(default_factory=list)
    stats: CrawlStats = Field(default_factory=CrawlStats)
    halted: bool = False
    halt_reason: str | None = None
    halt_url: str | None = None
    authenticated: bool = False


class CrawlHaltError(Exception):
    """Raised when crawl must stop (CAPTCHA, MFA, etc.) — SPEC §15.8–15.9."""

    def __init__(self, message: str, *, url: str | None = None, reason: str = "blocked") -> None:
        super().__init__(message)
        self.message = message
        self.url = url
        self.reason = reason
