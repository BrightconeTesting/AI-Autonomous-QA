"""Test case API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class TestCaseSummary(BaseModel):
    testcase_id: UUID
    name: str
    priority: str
    status: str
    flow_id: UUID | None = None
    feature: str | None = None
    tags: list[str] = Field(default_factory=list)
    step_count: int = 0
    created_at: datetime | None = None


class TestCaseListResponse(BaseModel):
    items: list[TestCaseSummary]
    total: int


class TestCaseDetailResponse(BaseModel):
    testcase_id: UUID
    app_id: UUID
    name: str
    priority: str
    status: str
    flow_id: UUID | None = None
    steps: dict[str, Any]
    pipeline_run_id: UUID | None = None
