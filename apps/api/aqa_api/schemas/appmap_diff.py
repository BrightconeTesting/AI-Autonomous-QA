"""AppMap diff API schemas (DISCOVERY-AGENT-VISION-SPEC §10.4)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AppMapDiffPageRef(BaseModel):
    page_id: str
    url: str
    title: str | None = None
    changed_fields: list[str] = Field(default_factory=list)


class AppMapDiffElementDelta(BaseModel):
    page_id: str
    from_count: int = 0
    to_count: int = 0
    delta: int = 0


class AppMapDiffApiRef(BaseModel):
    endpoint_id: str = ""
    method: str
    path: str


class AppMapDiffModuleSnapshot(BaseModel):
    module_id: str
    name: str
    parent_module_id: str | None = None
    pages: list[str] = Field(default_factory=list)
    flow_ids: list[str] = Field(default_factory=list)
    risk_score: int | None = None
    testability_score: int | None = None
    automation_complexity_score: int | None = None


class AppMapDiffModuleChange(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    module_id: str
    name: str
    changed_fields: list[str] = Field(default_factory=list)
    from_: AppMapDiffModuleSnapshot | None = Field(default=None, alias="from")
    to: AppMapDiffModuleSnapshot | None = None


class AppMapDiffScoreDelta(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: int = Field(alias="from")
    to: int
    delta: int


class AppMapDiffEntitySnapshot(BaseModel):
    entity_id: str
    name: str
    module_id: str | None = None
    crud_surfaces: dict[str, Any] = Field(default_factory=dict)


class AppMapDiffEntityCrudChange(BaseModel):
    entity_id: str
    name: str
    from_crud_surfaces: dict[str, Any] = Field(default_factory=dict)
    to_crud_surfaces: dict[str, Any] = Field(default_factory=dict)


class AppMapDiffAreaRef(BaseModel):
    area_id: str
    area: str | None = None
    priority_index: int | None = None
    area_type: str | None = None


class AppMapDiffPages(BaseModel):
    added: list[AppMapDiffPageRef] = Field(default_factory=list)
    removed: list[AppMapDiffPageRef] = Field(default_factory=list)
    changed: list[AppMapDiffPageRef] = Field(default_factory=list)


class AppMapDiffElements(BaseModel):
    delta_by_page: list[AppMapDiffElementDelta] = Field(default_factory=list)


class AppMapDiffApiEndpoints(BaseModel):
    added: list[AppMapDiffApiRef] = Field(default_factory=list)
    removed: list[AppMapDiffApiRef] = Field(default_factory=list)


class AppMapDiffDependencyGraph(BaseModel):
    edges_added: list[dict[str, Any]] = Field(default_factory=list)
    edges_removed: list[dict[str, Any]] = Field(default_factory=list)


class AppMapDiffModules(BaseModel):
    added: list[AppMapDiffModuleSnapshot] = Field(default_factory=list)
    removed: list[AppMapDiffModuleSnapshot] = Field(default_factory=list)
    changed: list[AppMapDiffModuleChange] = Field(default_factory=list)


class AppMapDiffEntities(BaseModel):
    added: list[AppMapDiffEntitySnapshot] = Field(default_factory=list)
    removed: list[AppMapDiffEntitySnapshot] = Field(default_factory=list)
    crud_surfaces_changed: list[AppMapDiffEntityCrudChange] = Field(default_factory=list)


class AppMapDiffRecommendedAreas(BaseModel):
    added: list[AppMapDiffAreaRef] = Field(default_factory=list)
    removed: list[AppMapDiffAreaRef] = Field(default_factory=list)


class AppMapDiffResponse(BaseModel):
    application_id: UUID
    from_run_id: UUID
    to_run_id: UUID
    from_appmap_hash: str | None = None
    to_appmap_hash: str | None = None
    unchanged: bool = False
    pages: AppMapDiffPages = Field(default_factory=AppMapDiffPages)
    elements: AppMapDiffElements = Field(default_factory=AppMapDiffElements)
    api_endpoints: AppMapDiffApiEndpoints = Field(default_factory=AppMapDiffApiEndpoints)
    api_dependency_graph: AppMapDiffDependencyGraph = Field(default_factory=AppMapDiffDependencyGraph)
    modules: AppMapDiffModules = Field(default_factory=AppMapDiffModules)
    scores: dict[str, AppMapDiffScoreDelta] = Field(default_factory=dict)
    entities: AppMapDiffEntities = Field(default_factory=AppMapDiffEntities)
    recommended_test_areas: AppMapDiffRecommendedAreas = Field(default_factory=AppMapDiffRecommendedAreas)


class DiscoverRunSummary(BaseModel):
    pipeline_run_id: UUID
    started_at: str | None = None
    ended_at: str | None = None
    appmap_hash: str | None = None
    has_artifact: bool = False
    page_count: int | None = None
    element_count: int | None = None
    flow_count: int | None = None


class DiscoverRunListResponse(BaseModel):
    items: list[DiscoverRunSummary] = Field(default_factory=list)
    total: int = 0
