"""Pipeline SSE event response schemas (SPEC §16.7, Day 14)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from aqa_shared.sse.events import PipelineEventType


class StageStartedData(BaseModel):
    stage: str


class StageProgressData(BaseModel):
    pages_discovered: int | None = None
    max_pages: int | None = None


class StageCompletedData(BaseModel):
    stage: str
    duration_ms: int | None = None


class StageFailedData(BaseModel):
    error: str
    stage: str | None = None


class PipelineCompletedData(BaseModel):
    status: str


class PipelineSseEventPayload(BaseModel):
    """Documented SSE `data` field shape (all events include pipeline_run_id + timestamp)."""

    pipeline_run_id: UUID
    timestamp: datetime
    stage: str | None = None
    pages_discovered: int | None = None
    max_pages: int | None = None
    duration_ms: int | None = None
    error: str | None = None
    status: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


PIPELINE_SSE_EVENT_TYPES = [event.value for event in PipelineEventType]


class PipelineEventListItem(BaseModel):
    id: str
    event: str
    data: dict[str, Any] = Field(default_factory=dict)
