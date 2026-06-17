"""Persist crawl results to pages, elements, and artifacts (Day 19)."""

from __future__ import annotations

import hashlib
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from aqa_discovery.types import CrawlResult, PageSnapshot
from aqa_shared.db.models import (
    Application,
    Artifact,
    ArtifactType,
    Element,
    Page,
    PipelineRun,
    PipelineStage,
    PipelineStatus,
)

logger = logging.getLogger(__name__)

DEFAULT_ARTIFACT_ROOT = "./artifacts"


@dataclass(frozen=True)
class PersistResult:
    page_count: int
    element_count: int
    artifact_count: int


def artifact_storage_root() -> Path:
    return Path(os.getenv("ARTIFACT_STORAGE_PATH", DEFAULT_ARTIFACT_ROOT)).resolve()


def screenshot_path_for_page(*, app_id: uuid.UUID, url: str) -> Path:
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return artifact_storage_root() / "screenshots" / str(app_id) / f"{url_hash}.png"


def mark_pipeline_running(db: Session, pipeline_run_id: uuid.UUID) -> None:
    run = db.get(PipelineRun, pipeline_run_id)
    if run is None:
        raise ValueError(f"Pipeline run not found: {pipeline_run_id}")
    run.status = PipelineStatus.running
    run.current_stage = PipelineStage.discover
    if run.started_at is None:
        run.started_at = datetime.utcnow()
    db.commit()


def mark_pipeline_failed(
    db: Session,
    pipeline_run_id: uuid.UUID,
    *,
    error_message: str,
) -> None:
    run = db.get(PipelineRun, pipeline_run_id)
    if run is None:
        return
    run.status = PipelineStatus.failed
    run.error_message = error_message[:2000]
    run.ended_at = datetime.utcnow()
    db.commit()


def mark_pipeline_completed(
    db: Session,
    pipeline_run_id: uuid.UUID,
    *,
    page_count: int,
    element_count: int,
) -> None:
    run = db.get(PipelineRun, pipeline_run_id)
    if run is None:
        raise ValueError(f"Pipeline run not found: {pipeline_run_id}")
    run.status = PipelineStatus.completed
    run.current_stage = PipelineStage.discover
    run.ended_at = datetime.utcnow()
    run.error_message = None
    config = dict(run.config or {})
    config["discovery_stats"] = {
        "page_count": page_count,
        "element_count": element_count,
    }
    run.config = config
    db.commit()


def update_last_crawl_at(db: Session, app_id: uuid.UUID) -> None:
    app = db.get(Application, app_id)
    if app is None:
        raise ValueError(f"Application not found: {app_id}")
    app.last_crawl_at = datetime.utcnow()
    db.commit()


def _upsert_page(
    db: Session,
    *,
    app_id: uuid.UUID,
    snapshot: PageSnapshot,
) -> Page:
    stmt = select(Page).where(Page.app_id == app_id, Page.url == snapshot.url)
    page = db.scalars(stmt).first()
    if page is None:
        page = Page(
            app_id=app_id,
            url=snapshot.url,
            title=snapshot.title[:512] if snapshot.title else None,
            screenshot_path=snapshot.screenshot_path,
        )
        db.add(page)
        db.flush()
        return page

    page.title = snapshot.title[:512] if snapshot.title else page.title
    page.screenshot_path = snapshot.screenshot_path or page.screenshot_path
    page.discovered_at = datetime.utcnow()
    db.flush()
    return page


def _replace_elements(db: Session, *, page_id: uuid.UUID, snapshot: PageSnapshot) -> int:
    db.execute(delete(Element).where(Element.page_id == page_id))
    count = 0
    for item in snapshot.elements:
        db.add(
            Element(
                page_id=page_id,
                tag_name=item.tag_name,
                role=item.role,
                text_content=item.text_content,
                semantic_selector=item.semantic_selector,
                xpath_fallback=item.xpath_fallback,
                attributes=item.attributes,
            )
        )
        count += 1
    return count


def _register_screenshot_artifact(
    db: Session,
    *,
    pipeline_run_id: uuid.UUID,
    screenshot_path: str,
) -> None:
    path = Path(screenshot_path)
    if not path.is_file():
        return

    existing = db.scalars(
        select(Artifact).where(
            Artifact.pipeline_run_id == pipeline_run_id,
            Artifact.type == ArtifactType.screenshot,
            Artifact.path == screenshot_path,
        )
    ).first()
    if existing is not None:
        return

    db.add(
        Artifact(
            pipeline_run_id=pipeline_run_id,
            type=ArtifactType.screenshot,
            path=screenshot_path,
            size_bytes=path.stat().st_size,
        )
    )


def persist_crawl_result(
    db: Session,
    *,
    app_id: uuid.UUID,
    pipeline_run_id: uuid.UUID,
    crawl_result: CrawlResult,
) -> PersistResult:
    """Upsert pages/elements and register screenshot artifacts."""
    page_count = 0
    element_count = 0
    artifact_count = 0

    for snapshot in crawl_result.pages:
        page = _upsert_page(db, app_id=app_id, snapshot=snapshot)
        element_count += _replace_elements(db, page_id=page.page_id, snapshot=snapshot)
        page_count += 1

        if snapshot.screenshot_path:
            _register_screenshot_artifact(
                db,
                pipeline_run_id=pipeline_run_id,
                screenshot_path=snapshot.screenshot_path,
            )
            artifact_count += 1

    db.commit()
    logger.info(
        "DiscoveryWorker persisted crawl result",
        extra={
            "applicationId": str(app_id),
            "pipelineRunId": str(pipeline_run_id),
            "pageCount": page_count,
            "elementCount": element_count,
            "artifactCount": artifact_count,
        },
    )
    return PersistResult(
        page_count=page_count,
        element_count=element_count,
        artifact_count=artifact_count,
    )
