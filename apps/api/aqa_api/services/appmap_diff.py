"""AppMap diff read service (Phase E)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from aqa_agents.discovery.appmap_diff import AppMapDiffError, diff_appmap_runs, list_discover_runs
from aqa_api.schemas.appmap_diff import AppMapDiffResponse, DiscoverRunListResponse, DiscoverRunSummary
from aqa_api.services import applications as app_service


def get_appmap_diff(
    db: Session,
    app_id: UUID,
    *,
    from_run_id: UUID,
    to_run_id: UUID,
) -> AppMapDiffResponse | None:
    if app_service.get_application(db, app_id) is None:
        return None
    raw = diff_appmap_runs(
        db,
        app_id=app_id,
        from_run_id=from_run_id,
        to_run_id=to_run_id,
    )
    return AppMapDiffResponse.model_validate(raw)


def list_app_discover_runs(db: Session, app_id: UUID) -> DiscoverRunListResponse | None:
    if app_service.get_application(db, app_id) is None:
        return None
    items = [
        DiscoverRunSummary.model_validate(item)
        for item in list_discover_runs(db, app_id)
    ]
    return DiscoverRunListResponse(items=items, total=len(items))


__all__ = ["AppMapDiffError", "get_appmap_diff", "list_app_discover_runs"]
