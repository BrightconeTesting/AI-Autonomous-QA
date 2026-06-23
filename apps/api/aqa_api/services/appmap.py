"""AppMap read service (Day 20)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from aqa_agents.discovery.appmap import load_appmap_for_application
from aqa_api.schemas.appmap import (
    AppMapElement,
    AppMapFlow,
    AppMapApiEndpoint,
    AppMapApiUiMapping,
    AppMapDataEntity,
    ApiDependencyGraph,
    AuthIntelligence,
    AppMapForm,
    AppMapModule,
    AppMapPage,
    AppMapResponse,
    AppMapSpaRoute,
    AppMapState,
    AppMapStats,
    AppMapTransition,
    NavigationGraphEdge,
    ScoringSummary,
    TestDataCatalogEntry,
)


def get_appmap(db: Session, app_id: UUID) -> AppMapResponse | None:
    raw = load_appmap_for_application(db, app_id)
    if raw is None:
        return None
    stats_raw = raw.get("stats") or {}
    scoring_raw = raw.get("scoring_summary")
    return AppMapResponse(
        schema_version=int(raw.get("schema_version") or 1),
        application_id=UUID(str(raw["application_id"])),
        last_crawl_at=raw.get("last_crawl_at"),
        mvp=raw.get("mvp"),
        discovery_completeness_score=raw.get("discovery_completeness_score"),
        recommendations=list(raw.get("recommendations") or []),
        scoring_summary=ScoringSummary.model_validate(scoring_raw)
        if isinstance(scoring_raw, dict)
        else None,
        pages=[AppMapPage.model_validate(page) for page in raw.get("pages") or []],
        elements=[AppMapElement.model_validate(element) for element in raw.get("elements") or []],
        flows=[AppMapFlow.model_validate(flow) for flow in raw.get("flows") or []],
        stats=AppMapStats.model_validate(stats_raw),
        states=[AppMapState.model_validate(state) for state in raw.get("states") or []],
        transitions=[
            AppMapTransition.model_validate(transition) for transition in raw.get("transitions") or []
        ],
        modules=[AppMapModule.model_validate(module) for module in raw.get("modules") or []],
        navigation_graph=[
            NavigationGraphEdge.model_validate(edge) for edge in raw.get("navigation_graph") or []
        ],
        forms=[AppMapForm.model_validate(form) for form in raw.get("forms") or []],
        api_endpoints=[
            AppMapApiEndpoint.model_validate(endpoint) for endpoint in raw.get("api_endpoints") or []
        ],
        api_ui_mappings=[
            AppMapApiUiMapping.model_validate(mapping) for mapping in raw.get("api_ui_mappings") or []
        ],
        data_entities=[
            AppMapDataEntity.model_validate(entity) for entity in raw.get("data_entities") or []
        ],
        api_dependency_graph=ApiDependencyGraph.model_validate(raw["api_dependency_graph"])
        if isinstance(raw.get("api_dependency_graph"), dict)
        else None,
        auth_intelligence=AuthIntelligence.model_validate(raw["auth_intelligence"])
        if isinstance(raw.get("auth_intelligence"), dict)
        else None,
        test_data_catalog=[
            TestDataCatalogEntry.model_validate(entry) for entry in raw.get("test_data_catalog") or []
        ],
        spa_routes=[AppMapSpaRoute.model_validate(route) for route in raw.get("spa_routes") or []],
    )
