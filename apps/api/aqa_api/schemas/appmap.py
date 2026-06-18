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
    state_id: UUID | None = None


class AppMapFlow(BaseModel):
    flow_id: UUID
    name: str
    description: str | None = None
    source: str
    steps: list[dict[str, Any]] = Field(default_factory=list)


class AppMapState(BaseModel):
    state_id: UUID
    page_id: UUID
    state_key: str
    fingerprint: str | None = None
    title: str | None = None
    interaction_depth: int = 0
    parent_state_key: str | None = None
    trigger_action: dict[str, Any] = Field(default_factory=dict)


class AppMapTransition(BaseModel):
    transition_id: UUID
    from_state_id: UUID
    to_state_id: UUID
    action: dict[str, Any] = Field(default_factory=dict)


class AppMapStats(BaseModel):
    page_count: int = 0
    element_count: int = 0
    flow_count: int = 0
    state_count: int = 0
    interaction_count: int = 0


class AppMapResponse(BaseModel):
    schema_version: int = 1
    application_id: UUID
    last_crawl_at: datetime | None = None
    pages: list[AppMapPage]
    elements: list[AppMapElement]
    flows: list[AppMapFlow]
    stats: AppMapStats
    states: list[AppMapState] = Field(default_factory=list)
    transitions: list[AppMapTransition] = Field(default_factory=list)
