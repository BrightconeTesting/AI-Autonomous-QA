"""Discovery worker data types."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PageSnapshot(BaseModel):
    url: str
    title: str
    status: int
    html_length: int = Field(ge=0)
    depth: int = Field(default=0, ge=0)


class CrawlStats(BaseModel):
    pages_crawled: int = 0
    skipped_off_domain: int = 0
    skipped_excluded: int = 0
    skipped_duplicate: int = 0
    max_pages: int = 0
    max_depth: int = 0


class CrawlResult(BaseModel):
    pages: list[PageSnapshot] = Field(default_factory=list)
    stats: CrawlStats = Field(default_factory=CrawlStats)
