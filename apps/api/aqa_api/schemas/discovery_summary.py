"""Discovery summary API schemas (DISCOVERY-AGENT-VISION-SPEC §10.3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from aqa_api.schemas.appmap import ScoringSummary


class DiscoverySummaryCounts(BaseModel):
    pages: int = 0
    buttons: int = 0
    forms: int = 0
    links: int = 0
    api_endpoints: int = 0
    flows: int = 0
    entities: int = 0
    modules: int = 0
    spa_routes: int = 0
    api_dependency_edges: int = 0


class DiscoverySummaryForm(BaseModel):
    name: str
    page: str


class DiscoverySummaryApiCall(BaseModel):
    method: str
    path: str


class DiscoverySummaryRiskArea(BaseModel):
    module: str
    risk_score: int
    top_factor: str


class DiscoverySummaryModuleNode(BaseModel):
    name: str
    children: list[str] = Field(default_factory=list)


class DiscoverySummaryAuth(BaseModel):
    session_type: str = "unknown"
    personas_authenticated: list[str] = Field(default_factory=list)


class DiscoverySummaryResponse(BaseModel):
    application_id: UUID
    last_crawl_at: datetime | None = None
    schema_version: int = 1
    counts: DiscoverySummaryCounts
    scoring_summary: ScoringSummary | None = None
    discovery_completeness_score: int = 0
    recommendations: list[str] = Field(default_factory=list)
    what_pages_exist: list[str] = Field(default_factory=list)
    what_forms_exist: list[DiscoverySummaryForm] = Field(default_factory=list)
    what_apis_are_called: list[DiscoverySummaryApiCall] = Field(default_factory=list)
    what_should_be_tested_first: list[str] = Field(default_factory=list)
    top_risk_areas: list[DiscoverySummaryRiskArea] = Field(default_factory=list)
    module_tree: list[DiscoverySummaryModuleNode] = Field(default_factory=list)
    auth_summary: DiscoverySummaryAuth = Field(default_factory=DiscoverySummaryAuth)
