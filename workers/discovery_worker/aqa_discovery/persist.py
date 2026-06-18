"""Persist crawl results to pages, elements, states, and artifacts."""

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

from aqa_discovery.types import CrawlResult, PageSnapshot, UIStateSnapshot
from aqa_shared.db.models import (
    Application,
    Artifact,
    ArtifactType,
    Element,
    Page,
    PageDiscovery,
    PageState,
    PipelineRun,
    PipelineStage,
    PipelineStatus,
    StateTransition,
)

logger = logging.getLogger(__name__)

DEFAULT_ARTIFACT_ROOT = "./artifacts"


@dataclass(frozen=True)
class PersistResult:
    page_count: int
    element_count: int
    state_count: int
    artifact_count: int


def artifact_storage_root() -> Path:
    return Path(os.getenv("ARTIFACT_STORAGE_PATH", DEFAULT_ARTIFACT_ROOT)).resolve()


def screenshot_path_for_page(*, app_id: uuid.UUID, url: str) -> Path:
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return artifact_storage_root() / "screenshots" / str(app_id) / f"{url_hash}.png"


def screenshot_path_for_state(*, app_id: uuid.UUID, url: str, state_key: str) -> Path:
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return artifact_storage_root() / "screenshots" / str(app_id) / f"{url_hash}_{state_key}.png"


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
    state_count: int = 0,
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
        "state_count": state_count,
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


def _replace_page_cic_data(
    db: Session,
    *,
    app_id: uuid.UUID,
    page: Page,
    snapshot: PageSnapshot,
) -> tuple[int, int]:
    """Replace states, transitions, and state-scoped elements for a page."""
    state_ids = list(
        db.scalars(select(PageState.state_id).where(PageState.page_id == page.page_id)).all()
    )
    if state_ids:
        db.execute(delete(StateTransition).where(StateTransition.from_state_id.in_(state_ids)))
    db.execute(delete(PageState).where(PageState.page_id == page.page_id))
    db.execute(delete(Element).where(Element.page_id == page.page_id))
    db.flush()

    element_count = 0
    state_key_to_id: dict[str, uuid.UUID] = {}

    states = snapshot.states or []
    if not states:
        element_count = _replace_baseline_elements(db, page_id=page.page_id, snapshot=snapshot)
        return 0, element_count

    for state_snap in states:
        state_row = PageState(
            page_id=page.page_id,
            state_key=state_snap.state_key,
            fingerprint=state_snap.fingerprint,
            title=state_snap.title[:512] if state_snap.title else None,
            screenshot_path=state_snap.screenshot_path,
            interaction_depth=state_snap.interaction_depth,
            parent_state_key=state_snap.parent_state_key,
            trigger_action=state_snap.trigger_interaction.model_dump() if state_snap.trigger_interaction else {},
        )
        db.add(state_row)
        db.flush()
        state_key_to_id[state_snap.state_key] = state_row.state_id
        element_count += _replace_state_elements(db, page_id=page.page_id, state_id=state_row.state_id, state=state_snap)

    for transition in snapshot.transitions:
        from_id = state_key_to_id.get(transition.from_state_key)
        to_id = state_key_to_id.get(transition.to_state_key)
        if from_id is None or to_id is None:
            continue
        db.add(
            StateTransition(
                app_id=app_id,
                from_state_id=from_id,
                to_state_id=to_id,
                action=transition.action.model_dump(),
            )
        )

    return len(states), element_count


def _replace_baseline_elements(db: Session, *, page_id: uuid.UUID, snapshot: PageSnapshot) -> int:
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


def _replace_state_elements(
    db: Session,
    *,
    page_id: uuid.UUID,
    state_id: uuid.UUID,
    state: UIStateSnapshot,
) -> int:
    count = 0
    for item in state.elements:
        db.add(
            Element(
                page_id=page_id,
                state_id=state_id,
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


def _upsert_page_discoveries(
    db: Session,
    *,
    app_id: uuid.UUID,
    page: Page,
    snapshot: PageSnapshot,
) -> None:
    seen_urls: set[str] = set()
    for discovery in snapshot.discovered_urls:
        if discovery.url in seen_urls:
            continue
        seen_urls.add(discovery.url)
        existing = db.scalars(
            select(PageDiscovery).where(PageDiscovery.app_id == app_id, PageDiscovery.url == discovery.url)
        ).first()
        if existing is not None:
            continue
        db.add(
            PageDiscovery(
                app_id=app_id,
                url=discovery.url,
                discovered_via=discovery.discovered_via,
                source_page_id=page.page_id,
                source_state_key=discovery.source_state_key,
                trigger_action=discovery.trigger_interaction.model_dump() if discovery.trigger_interaction else {},
            )
        )


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
    """Upsert pages, states, elements, discoveries; register screenshot artifacts."""
    page_count = 0
    element_count = 0
    state_count = 0
    artifact_count = 0
    screenshot_paths: set[str] = set()

    for snapshot in crawl_result.pages:
        page = _upsert_page(db, app_id=app_id, snapshot=snapshot)
        states, elements = _replace_page_cic_data(db, app_id=app_id, page=page, snapshot=snapshot)
        state_count += states
        element_count += elements
        page_count += 1

        if snapshot.discovered_urls:
            _upsert_page_discoveries(db, app_id=app_id, page=page, snapshot=snapshot)

        if snapshot.screenshot_path:
            screenshot_paths.add(snapshot.screenshot_path)
        for state in snapshot.states:
            if state.screenshot_path:
                screenshot_paths.add(state.screenshot_path)

    for path in screenshot_paths:
        _register_screenshot_artifact(db, pipeline_run_id=pipeline_run_id, screenshot_path=path)
        artifact_count += 1

    db.commit()
    logger.info(
        "DiscoveryWorker persisted crawl result",
        extra={
            "applicationId": str(app_id),
            "pipelineRunId": str(pipeline_run_id),
            "pageCount": page_count,
            "stateCount": state_count,
            "elementCount": element_count,
            "artifactCount": artifact_count,
        },
    )
    return PersistResult(
        page_count=page_count,
        element_count=element_count,
        state_count=state_count,
        artifact_count=artifact_count,
    )
