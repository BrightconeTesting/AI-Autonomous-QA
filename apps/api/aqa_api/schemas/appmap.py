"""AppMap API response schemas (SPEC §16.7, Day 20)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AppMapPage(BaseModel):
    page_id: UUID
    url: str
    title: str | None = None
    screenshot_path: str | None = None


class AppMapElement(BaseModel):
    element_id: UUID
    page_id: UUID
    tag_name: str
    role: str | None = None
    semantic_selector: str | None = None
    xpath_fallback: str | None = None
    text_content: str | None = None


class AppMapFlow(BaseModel):
    flow_id: UUID
    name: str
    description: str | None = None
    source: str
    steps: list[dict[str, Any]] = Field(default_factory=list)


class AppMapStats(BaseModel):
    page_count: int = 0
    element_count: int = 0
    flow_count: int = 0


class AppMapResponse(BaseModel):
    application_id: UUID
    last_crawl_at: datetime | None = None
    pages: list[AppMapPage]
    elements: list[AppMapElement]
    flows: list[AppMapFlow]
    stats: AppMapStats
