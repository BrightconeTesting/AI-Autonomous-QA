"""AppMap approval workflow schemas (DISCOVERY-AGENT-VISION-SPEC §19.3)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AppMapApprovalStatusResponse(BaseModel):
    application_id: UUID
    pipeline_run_id: UUID | None = None
    status: str = Field(description="pending | approved | rejected | none")
    approved_at: datetime | None = None
    rejection_reason: str | None = None


class AppMapRejectRequest(BaseModel):
    reason: str = Field(default="", max_length=2000)


class AppMapApprovalResponse(BaseModel):
    application_id: UUID
    pipeline_run_id: UUID
    status: str
    approved_at: datetime | None = None
    rejection_reason: str | None = None
