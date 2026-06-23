"""Discovery summary read service (DISCOVERY-AGENT-VISION-SPEC §10.3)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from aqa_agents.discovery.appmap import load_appmap_for_application
from aqa_agents.discovery.discovery_summary import build_discovery_summary
from aqa_api.schemas.discovery_summary import DiscoverySummaryResponse
from aqa_shared.db.models import Application


def get_discovery_summary(db: Session, app_id: UUID) -> DiscoverySummaryResponse | None:
    app = db.get(Application, app_id)
    if app is None:
        return None

    raw = load_appmap_for_application(db, app_id)
    if raw is None:
        return None

    summary = build_discovery_summary(raw, auth_config=dict(app.auth_config or {}))
    return DiscoverySummaryResponse.model_validate(summary)
