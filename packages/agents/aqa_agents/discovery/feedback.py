"""Discovery execution feedback — agent integration (Phase H)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from aqa_shared.db.models import Application
from aqa_shared.discovery.feedback import (
    append_feedback_to_crawl_config,
    apply_discovery_feedback,
    build_feedback_event,
    classify_execution_failure,
    normalize_feedback_events,
    urls_requiring_recrawl,
)

__all__ = [
    "apply_feedback_to_appmap",
    "ingest_execution_step_failure",
    "load_feedback_events",
    "urls_requiring_recrawl",
]


def load_feedback_events(crawl_config: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(crawl_config, dict):
        return []
    return normalize_feedback_events(crawl_config.get("discovery_feedback"))


def ingest_execution_step_failure(
    session: Session,
    *,
    app_id: uuid.UUID,
    pipeline_run_id: str,
    testcase_id: str,
    step_index: int,
    step: dict[str, Any],
    error_msg: str,
    page_url: str | None = None,
) -> dict[str, Any] | None:
    """Classify a failed execution step and append to application discovery_feedback."""
    failure_type = classify_execution_failure(error_msg, step=step, page_url=page_url)
    if failure_type is None:
        return None

    event = build_feedback_event(
        failure_type=failure_type,
        error_msg=error_msg,
        pipeline_run_id=pipeline_run_id,
        testcase_id=testcase_id,
        step_index=step_index,
        step=step,
        page_url=page_url or str(step.get("url") or ""),
    )

    app = session.get(Application, app_id)
    if app is None:
        return event

    crawl_config = app.crawl_config if isinstance(app.crawl_config, dict) else {}
    app.crawl_config = append_feedback_to_crawl_config(crawl_config, event)
    session.flush()
    return event


def apply_feedback_to_appmap(
    appmap: dict[str, Any],
    crawl_config: dict[str, Any] | None,
) -> dict[str, Any]:
    """Re-score AppMap artifacts using accumulated execution feedback."""
    events = load_feedback_events(crawl_config)
    return apply_discovery_feedback(appmap, events)
