"""Recommended test area decision schemas (Phase E §20.9)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class TestAreaDecisionItem(BaseModel):
    area_id: str
    status: str = Field(description="approved | dismissed")


class TestAreaDecisionsResponse(BaseModel):
    application_id: UUID
    pipeline_run_id: UUID
    decisions: dict[str, str] = Field(default_factory=dict)


class UpdateTestAreaDecisionsRequest(BaseModel):
    decisions: list[TestAreaDecisionItem] = Field(default_factory=list)
