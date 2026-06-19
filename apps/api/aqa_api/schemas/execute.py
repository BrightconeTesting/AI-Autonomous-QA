"""Execute API schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ExecuteRequest(BaseModel):
    testcase_ids: list[UUID] | None = None
    capture_video: bool = True
    capture_trace: bool = True
    retry_from_run_id: UUID | None = None
    retry_mode: str | None = None
    force: bool = False


class ExecuteResponse(BaseModel):
    pipeline_run_id: UUID
    application_id: UUID
    test_run_id: UUID
    status: str
    current_stage: str
    started_at: datetime
