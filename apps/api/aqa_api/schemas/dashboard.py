"""Dashboard summary schemas (DASHBOARD-SPEC Phase 4)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from aqa_api.schemas.runs import RunSummary


class DashboardRecentRun(BaseModel):
    run_id: UUID
    app_id: UUID
    app_name: str
    status: str
    started_at: datetime | None = None
    summary: RunSummary = Field(default_factory=RunSummary)


class DashboardSummaryResponse(BaseModel):
    app_count: int = 0
    total_runs: int = 0
    total_passed: int = 0
    total_failed: int = 0
    storage_bytes: int = 0
    recent_runs: list[DashboardRecentRun] = Field(default_factory=list)
