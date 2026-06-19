"""Pipeline run API schemas (SPEC §16.3, Day 13)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class DiscoverRequest(BaseModel):
    force: bool = False
    crawl_config_overrides: dict[str, Any] | None = Field(default=None, alias="crawlConfigOverrides")

    model_config = {"populate_by_name": True}


class DiscoverResponse(BaseModel):
    pipeline_run_id: UUID
    application_id: UUID
    status: str
    current_stage: str
    started_at: datetime


class PipelineRunResponse(BaseModel):
    pipeline_run_id: UUID
    application_id: UUID
    status: str
    current_stage: str
    config: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    llm_tokens_used: int = 0
    cost_estimate: float = 0.0
    error_message: str | None = None


class ActivePipelineResponse(BaseModel):
    pipeline_run: PipelineRunResponse | None = None
