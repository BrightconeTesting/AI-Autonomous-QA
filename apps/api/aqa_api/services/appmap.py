"""AppMap read service (Day 20)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from aqa_agents.discovery.appmap import load_appmap_for_application
from aqa_api.schemas.appmap import (
    AppMapElement,
    AppMapFlow,
    AppMapPage,
    AppMapResponse,
    AppMapState,
    AppMapStats,
    AppMapTransition,
)


def get_appmap(db: Session, app_id: UUID) -> AppMapResponse | None:
    raw = load_appmap_for_application(db, app_id)
    if raw is None:
        return None
    stats_raw = raw.get("stats") or {}
    return AppMapResponse(
        schema_version=int(raw.get("schema_version") or 1),
        application_id=UUID(str(raw["application_id"])),
        last_crawl_at=raw.get("last_crawl_at"),
        pages=[AppMapPage.model_validate(page) for page in raw.get("pages") or []],
        elements=[AppMapElement.model_validate(element) for element in raw.get("elements") or []],
        flows=[AppMapFlow.model_validate(flow) for flow in raw.get("flows") or []],
        stats=AppMapStats.model_validate(stats_raw),
        states=[AppMapState.model_validate(state) for state in raw.get("states") or []],
        transitions=[
            AppMapTransition.model_validate(transition) for transition in raw.get("transitions") or []
        ],
    )
