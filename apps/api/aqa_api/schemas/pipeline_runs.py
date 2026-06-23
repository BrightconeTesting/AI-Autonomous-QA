"""Pipeline run API schemas (SPEC §16.3, Day 13)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class LlmBudgetsConfig(BaseModel):
    flow_structure: int = Field(default=3000, ge=0)
    module_structure: int = Field(default=2500, ge=0)
    entities: int = Field(default=2000, ge=0)
    test_areas: int = Field(default=2000, ge=0)
    total_cap: int = Field(default=8000, ge=0, alias="totalCap")

    model_config = {"populate_by_name": True}

    def to_dict(self) -> dict[str, int]:
        return {
            "flow_structure": self.flow_structure,
            "module_structure": self.module_structure,
            "entities": self.entities,
            "test_areas": self.test_areas,
            "total_cap": self.total_cap,
        }


class DiscoverPersonaConfig(BaseModel):
    persona_id: str = Field(alias="personaId")
    label: str | None = None
    auth_config: dict[str, Any] = Field(default_factory=dict, alias="authConfig")

    model_config = {"populate_by_name": True}


class DiscoverRequest(BaseModel):
    force: bool = False
    use_llm: bool = True
    openapi_url: str | None = Field(default=None, alias="openapiUrl")
    capture_network: bool = Field(default=True, alias="captureNetwork")
    capture_har: bool = Field(default=False, alias="captureHar")
    crawl_config_overrides: dict[str, Any] | None = Field(default=None, alias="crawlConfigOverrides")
    llm_budgets: LlmBudgetsConfig | None = Field(default=None, alias="llmBudgets")
    personas: list[DiscoverPersonaConfig] = Field(default_factory=list)

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
