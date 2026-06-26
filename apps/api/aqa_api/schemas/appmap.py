"""AppMap API response schemas (SPEC §16.7, Day 20)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AppMapPage(BaseModel):
    page_id: UUID
    url: str
    title: str | None = None
    screenshot_path: str | None = None


class AppMapElement(BaseModel):
    element_id: UUID
    page_id: UUID
    tag_name: str
    role: str | None = None
    semantic_selector: str | None = None
    xpath_fallback: str | None = None
    text_content: str | None = None
    state_id: UUID | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class AppMapFlow(BaseModel):
    flow_id: UUID
    name: str
    description: str | None = None
    source: str
    steps: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float | None = None
    confidence_factors: list[str] = Field(default_factory=list)
    review_required: bool | None = None
    module: str | None = None
    module_id: str | None = None
    risk_score: int | None = None
    risk_factors: list[str] = Field(default_factory=list)
    testability_score: int | None = None
    automation_complexity_score: int | None = None
    complexity_factors: list[str] = Field(default_factory=list)


class AppMapModuleFeature(BaseModel):
    name: str
    flow_id: UUID | None = None
    page_ids: list[str] = Field(default_factory=list)


class AppMapModule(BaseModel):
    module_id: str
    name: str
    parent_module_id: str | None = None
    pages: list[str] = Field(default_factory=list)
    flow_ids: list[str] = Field(default_factory=list)
    features: list[AppMapModuleFeature] = Field(default_factory=list)
    confidence: float | None = None
    confidence_factors: list[str] = Field(default_factory=list)
    review_required: bool | None = None
    risk_score: int | None = None
    risk_factors: list[str] = Field(default_factory=list)
    testability_score: int | None = None
    automation_complexity_score: int | None = None
    complexity_factors: list[str] = Field(default_factory=list)
    business_criticality: str | None = None
    priority_index: int | None = None
    recommended_test_areas: list[RecommendedTestArea] = Field(default_factory=list)


class NavigationGraphEdge(BaseModel):
    from_page_id: str | None = None
    to_page_id: str | None = None
    to_url: str | None = None
    via: str | None = None
    label: str | None = None


class AppMapState(BaseModel):
    state_id: UUID
    page_id: UUID
    state_key: str
    fingerprint: str | None = None
    title: str | None = None
    interaction_depth: int = 0
    parent_state_key: str | None = None
    trigger_action: dict[str, Any] = Field(default_factory=dict)


class AppMapTransition(BaseModel):
    transition_id: UUID
    from_state_id: UUID
    to_state_id: UUID
    action: dict[str, Any] = Field(default_factory=dict)


class AppMapStats(BaseModel):
    page_count: int = 0
    element_count: int = 0
    flow_count: int = 0
    state_count: int = 0
    interaction_count: int = 0
    module_count: int = 0
    form_count: int = 0
    api_endpoint_count: int = 0
    api_ui_mapping_count: int = 0
    entity_count: int = 0
    api_dependency_edge_count: int = 0
    test_data_catalog_count: int = 0
    spa_route_count: int = 0
    recommended_test_area_count: int = 0


class RecommendedTestArea(BaseModel):
    area_id: str
    area: str
    area_type: str | None = None
    priority: str = "medium"
    priority_index: int = 0
    rationale: str | None = None
    signals: list[str] = Field(default_factory=list)
    module_id: str | None = None
    page_id: str | None = None
    form_id: str | None = None
    api_endpoint_id: str | None = None
    element_id: str | None = None
    entity_id: str | None = None
    risk_score: int | None = None
    confidence: float | None = None
    confidence_factors: list[str] = Field(default_factory=list)
    review_required: bool | None = None


class AppMapSpaRoute(BaseModel):
    route_id: UUID
    path_pattern: str
    url_examples: list[str] = Field(default_factory=list)
    discovery_method: str = "pushstate_listener"
    discovery_methods: list[str] = Field(default_factory=list)
    page_id: str | None = None
    module_id: str | None = None
    confidence: float = 0.0


class TestDataCatalogField(BaseModel):
    name: str
    display_name: str | None = None
    data_type: str = "string"
    required: bool = False
    constraints: dict[str, Any] = Field(default_factory=dict)
    suggested_safe_value: str = ""
    pii_class: str | None = None
    element_id: str | None = None
    semantic_selector: str | None = None
    filled_during_crawl: bool = False
    needs_test_data: bool = True


class TestDataCatalogEntry(BaseModel):
    catalog_id: UUID
    target_type: str
    target_id: str
    fields: list[TestDataCatalogField] = Field(default_factory=list)
    synthetic_strategy: str = "deterministic_fixture"
    never_use_live_pii: bool = True
    state_key: str | None = None
    replay_steps: list[dict[str, Any]] = Field(default_factory=list)
    context_label: str | None = None
    unfilled_field_count: int = 0
    filled_during_crawl: bool = False
    reachable_via: list[str] = Field(default_factory=list)
    alias_target_ids: list[str] = Field(default_factory=list)


class AuthIntelligencePersona(BaseModel):
    persona_id: str
    label: str | None = None
    authenticated: bool = False
    visible_module_ids: list[str] = Field(default_factory=list)
    exclusive_module_ids: list[str] = Field(default_factory=list)


class AuthIntelligenceBlocker(BaseModel):
    type: str
    page_url: str | None = None
    message: str | None = None


class AuthIntelligence(BaseModel):
    session_type: str = "cookie"
    login_flow_id: str | None = None
    login_api_endpoint_id: str | None = None
    protected_page_ids: list[str] = Field(default_factory=list)
    protected_api_endpoint_ids: list[str] = Field(default_factory=list)
    cookie_names: list[str] = Field(default_factory=list)
    storage_keys: list[str] = Field(default_factory=list)
    personas: list[AuthIntelligencePersona] = Field(default_factory=list)
    visibility_matrix: dict[str, Any] = Field(default_factory=dict)
    blockers: list[AuthIntelligenceBlocker] = Field(default_factory=list)
    authenticated: bool = False


class ApiDependencyGraphEdge(BaseModel):
    from_endpoint_id: UUID
    to_endpoint_id: UUID
    edge_type: str
    confidence: float = 0.0
    observed_count: int = 1
    dependency_keys: list[str] = Field(default_factory=list)
    parallel_group_id: str | None = None
    is_primary: bool = True


class ApiDependencyGraphNode(BaseModel):
    endpoint_id: UUID
    method: str
    path: str
    path_pattern: str
    depth: int = 0
    module_id: str | None = None
    module_name: str | None = None
    requires_auth: bool = False
    auth_inherited_from: str | None = None
    risk_score: int | None = None
    risk_tier: str | None = None
    is_entry: bool = False
    is_leaf: bool = False
    seen_count: int = 1
    branching_factor: int = 0
    is_login_endpoint: bool = False
    is_session_check: bool = False


class ApiDependencyGraph(BaseModel):
    nodes: list[ApiDependencyGraphNode] = Field(default_factory=list)
    edges: list[ApiDependencyGraphEdge] = Field(default_factory=list)


class ApiFlowAnalysis(BaseModel):
    entry_endpoint_ids: list[str] = Field(default_factory=list)
    leaf_endpoint_ids: list[str] = Field(default_factory=list)
    critical_path_endpoint_ids: list[str] = Field(default_factory=list)
    max_depth: int = 0
    depth_counts: dict[str, int] = Field(default_factory=dict)
    parallel_group_count: int = 0


class ApiEndpointCoverage(BaseModel):
    covered_endpoint_ids: list[str] = Field(default_factory=list)
    planned_endpoint_ids: list[str] = Field(default_factory=list)
    untested_endpoint_ids: list[str] = Field(default_factory=list)
    unplanned_endpoint_ids: list[str] = Field(default_factory=list)


class AppMapDataEntity(BaseModel):
    entity_id: str
    name: str
    fields: list[str] = Field(default_factory=list)
    module_id: str | None = None
    business_criticality: str = "medium"
    risk_score: int | None = None
    confidence: float | None = None
    confidence_factors: list[str] = Field(default_factory=list)
    review_required: bool = False
    crud_surfaces: dict[str, Any] = Field(default_factory=dict)
    priority_index: int | None = None
    testability_score: int | None = None
    automation_complexity_score: int | None = None
    risk_factors: list[str] = Field(default_factory=list)


class AppMapApiUiMapping(BaseModel):
    mapping_id: UUID | None = None
    api_endpoint_id: UUID
    page_id: UUID
    form_id: UUID | None = None
    element_id: UUID | None = None
    flow_id: UUID | None = None
    trigger_action: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    correlation_method: str = "heuristic"
    review_required: bool = False


class AppMapForm(BaseModel):
    form_id: UUID
    page_id: UUID
    state_id: UUID | None = None
    name: str
    action: str | None = None
    method: str = "get"
    attributes: dict[str, Any] = Field(default_factory=dict)
    field_element_ids: list[str] = Field(default_factory=list)
    risk_score: int | None = None
    risk_factors: list[str] = Field(default_factory=list)
    testability_score: int | None = None
    priority_index: int | None = None


class AppMapApiEndpoint(BaseModel):
    endpoint_id: UUID
    method: str
    path: str
    path_pattern: str
    source: str = "network"
    request_schema: dict[str, Any] = Field(default_factory=dict)
    response_schema: dict[str, Any] = Field(default_factory=dict)
    seen_on_page_ids: list[str] = Field(default_factory=list)
    seen_count: int = 1
    risk_score: int | None = None
    risk_factors: list[str] = Field(default_factory=list)
    automation_complexity_score: int | None = None
    priority_index: int | None = None
    body_keys: list[str] = Field(default_factory=list)


class ScoringSummary(BaseModel):
    app_risk_score: int = 0
    app_testability_score: int = 0
    app_automation_complexity_score: int = 0
    discovery_completeness_score: int = 0
    high_risk_modules: list[str] = Field(default_factory=list)
    top_risk_modules: list[dict[str, Any]] = Field(default_factory=list)
    high_risk_form_count: int = 0
    mutating_api_count: int = 0
    scored_entity_count: int = 0
    recommendations: list[str] = Field(default_factory=list)


class AppMapResponse(BaseModel):
    schema_version: int = 1
    application_id: UUID
    last_crawl_at: datetime | None = None
    mvp: bool | None = None
    discovery_completeness_score: int | None = None
    recommendations: list[str] = Field(default_factory=list)
    scoring_summary: ScoringSummary | None = None
    pages: list[AppMapPage]
    elements: list[AppMapElement]
    flows: list[AppMapFlow]
    stats: AppMapStats
    states: list[AppMapState] = Field(default_factory=list)
    transitions: list[AppMapTransition] = Field(default_factory=list)
    modules: list[AppMapModule] = Field(default_factory=list)
    navigation_graph: list[NavigationGraphEdge] = Field(default_factory=list)
    forms: list[AppMapForm] = Field(default_factory=list)
    api_endpoints: list[AppMapApiEndpoint] = Field(default_factory=list)
    api_ui_mappings: list[AppMapApiUiMapping] = Field(default_factory=list)
    data_entities: list[AppMapDataEntity] = Field(default_factory=list)
    api_dependency_graph: ApiDependencyGraph | None = None
    api_flow_analysis: ApiFlowAnalysis | None = None
    api_coverage: ApiEndpointCoverage | None = None
    auth_intelligence: AuthIntelligence | None = None
    test_data_catalog: list[TestDataCatalogEntry] = Field(default_factory=list)
    spa_routes: list[AppMapSpaRoute] = Field(default_factory=list)
    recommended_test_areas: list[RecommendedTestArea] = Field(default_factory=list)
