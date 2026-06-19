"""Generate-tests API schemas (DASHBOARD-SPEC §10)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class GenerateTestsRequest(BaseModel):
    priorities: list[str] = Field(default_factory=lambda: ["critical", "high", "medium"])
    max_tests: int = Field(default=200, ge=1, le=200)
    use_llm: bool = True
    generate_scripts: bool = True
    require_appmap_v2: bool = Field(default=True, alias="requireAppmapV2")
    force: bool = False

    model_config = {"populate_by_name": True}


class GenerateTestsResponse(BaseModel):
    pipeline_run_id: UUID
    application_id: UUID
    status: str
    current_stage: str
    started_at: datetime
