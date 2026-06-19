"""Aggregate metrics for the dashboard home page."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aqa_api.schemas.dashboard import DashboardRecentRun, DashboardSummaryResponse
from aqa_api.schemas.runs import RunSummary
from aqa_api.services.artifacts import storage_bytes_for_app
from aqa_shared.db.models import Application, TestRun


def _run_summary(row: TestRun) -> RunSummary:
    raw = row.summary if isinstance(row.summary, dict) else {}
    return RunSummary(
        total=int(raw.get("total") or 0),
        passed=int(raw.get("passed") or 0),
        failed=int(raw.get("failed") or 0),
        skipped=int(raw.get("skipped") or 0),
    )


def get_dashboard_summary(db: Session, *, recent_limit: int = 10) -> DashboardSummaryResponse:
    apps = list(db.scalars(select(Application)).all())
    app_names = {a.app_id: a.name for a in apps}

    all_runs = list(db.scalars(select(TestRun)).all())
    total_runs = len(all_runs)
    total_passed = sum(_run_summary(r).passed for r in all_runs)
    total_failed = sum(_run_summary(r).failed for r in all_runs)
    storage_bytes = sum(storage_bytes_for_app(db, a.app_id) for a in apps)

    recent_rows = list(
        db.scalars(
            select(TestRun).order_by(TestRun.started_at.desc().nullslast()).limit(recent_limit)
        ).all()
    )

    recent = [
        DashboardRecentRun(
            run_id=row.run_id,
            app_id=row.app_id,
            app_name=app_names.get(row.app_id, "Unknown"),
            status=row.status.value if hasattr(row.status, "value") else str(row.status),
            started_at=row.started_at,
            summary=_run_summary(row),
        )
        for row in recent_rows
    ]

    return DashboardSummaryResponse(
        app_count=len(apps),
        total_runs=total_runs,
        total_passed=total_passed,
        total_failed=total_failed,
        storage_bytes=storage_bytes,
        recent_runs=recent,
    )
