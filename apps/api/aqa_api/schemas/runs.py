"""Test run API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class StepResult(BaseModel):
    index: int
    keyword: str | None = None
    text: str | None = None
    outcome: str
    duration_ms: int | None = None
    error: str | None = None


class ScenarioResult(BaseModel):
    testcase_id: UUID
    name: str
    outcome: str
    duration_ms: int | None = None
    artifact_ids: list[str] = Field(default_factory=list)
    video_artifact_id: str | None = None
    step_results: list[StepResult] = Field(default_factory=list)
    step_timestamps_ms: list[int] = Field(default_factory=list)
    error: str | None = None


class RunSummary(BaseModel):
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0


class TestRunSummary(BaseModel):
    run_id: UUID
    app_id: UUID
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    summary: RunSummary = Field(default_factory=RunSummary)


class TestRunListResponse(BaseModel):
    items: list[TestRunSummary]
    total: int


class TestRunDetailResponse(BaseModel):
    run_id: UUID
    app_id: UUID
    pipeline_run_id: UUID | None = None
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    summary: RunSummary = Field(default_factory=RunSummary)
    results: list[ScenarioResult] = Field(default_factory=list)


class ArtifactMetaResponse(BaseModel):
    id: UUID
    type: str
    size_bytes: int
    testcase_id: UUID | None = None
    run_id: UUID | None = None
    created_at: datetime
