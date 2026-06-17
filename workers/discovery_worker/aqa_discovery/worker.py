"""Discovery worker orchestration helpers."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from aqa_discovery.auth import AuthError, load_auth_config, write_credential_audit
from aqa_discovery.crawl_settings import CrawlSettings
from aqa_discovery.crawler import CrawlSession
from aqa_discovery.persist import (
    PersistResult,
    mark_pipeline_completed,
    mark_pipeline_failed,
    mark_pipeline_running,
    persist_crawl_result,
    update_last_crawl_at,
)
from aqa_discovery.types import CrawlResult, PageSnapshot
from aqa_discovery.url_utils import normalize_crawl_url
from aqa_shared.db.models import Application, CredentialAuditAction
from aqa_shared.db.session import get_session_factory
from aqa_shared.sse import PipelineEventType, publish_pipeline_event

logger = logging.getLogger(__name__)

DISCOVERY_STAGE = "discover"


def _build_start_urls(app: Application) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for candidate in [app.base_url, *(app.seed_urls or [])]:
        if not candidate:
            continue
        key = normalize_crawl_url(candidate)
        if key in seen:
            continue
        seen.add(key)
        urls.append(candidate)
    return urls


def _publish_crawl_progress(
    pipeline_run_id: str,
    *,
    pages_discovered: int,
    max_pages: int,
    current_url: str,
) -> None:
    publish_pipeline_event(
        pipeline_run_id,
        PipelineEventType.stage_progress,
        {
            "stage": DISCOVERY_STAGE,
            "pages_discovered": pages_discovered,
            "max_pages": max_pages,
            "current_url": current_url,
        },
    )


def crawl_application(
    application_id: str,
    *,
    crawl_overrides: dict | None = None,
    pipeline_run_id: str | None = None,
    persist: bool = True,
    db: Session | None = None,
) -> CrawlResult:
    """Load application config, authenticate when configured, and run BFS crawl."""
    owns_session = db is None
    session = db or get_session_factory()()
    pipeline_uuid = uuid.UUID(pipeline_run_id) if pipeline_run_id else None
    persist_enabled = persist and pipeline_uuid is not None

    try:
        app = session.get(Application, uuid.UUID(application_id))
        if app is None:
            raise ValueError(f"Application not found: {application_id}")

        if persist_enabled:
            mark_pipeline_running(session, pipeline_uuid)

        crawl_config = app.crawl_config if isinstance(app.crawl_config, dict) else {}
        settings = CrawlSettings.from_crawl_config(app.base_url, crawl_config, overrides=crawl_overrides)
        start_urls = _build_start_urls(app)

        def _audit(action: CredentialAuditAction) -> None:
            write_credential_audit(
                session,
                app_id=app.app_id,
                pipeline_run_id=pipeline_uuid,
                action=action,
            )

        stored_auth = app.auth_config if isinstance(app.auth_config, dict) else {}
        auth_config = load_auth_config(stored_auth, audit=_audit)
    except Exception:
        if owns_session:
            session.close()
        raise

    authenticated = False
    persist_result: PersistResult | None = None

    def _on_progress(_snapshot: PageSnapshot, stats) -> None:
        if pipeline_run_id:
            _publish_crawl_progress(
                pipeline_run_id,
                pages_discovered=stats.pages_crawled,
                max_pages=stats.max_pages,
                current_url=_snapshot.url,
            )

    try:
        with CrawlSession(
            page_timeout_ms=settings.page_timeout_ms,
            app_id=app.app_id if persist_enabled else None,
            capture_artifacts=persist_enabled,
        ) as crawl:
            if auth_config:
                try:
                    authenticated = crawl.authenticate(
                        auth_config=auth_config,
                        base_url=app.base_url,
                        audit=_audit,
                    )
                except AuthError as exc:
                    logger.warning(
                        "DiscoveryWorker authentication failed",
                        extra={"applicationId": application_id, "error": exc.message},
                    )
                    if persist_enabled and pipeline_uuid is not None:
                        mark_pipeline_failed(session, pipeline_uuid, error_message=exc.message)
                    return CrawlResult(
                        halted=True,
                        halt_reason=exc.message,
                        authenticated=False,
                    )

            result = crawl.crawl_bfs(start_urls, settings, on_progress=_on_progress if pipeline_run_id else None)
            result.authenticated = authenticated

            if persist_enabled and pipeline_uuid is not None and result.pages:
                try:
                    persist_result = persist_crawl_result(
                        session,
                        app_id=app.app_id,
                        pipeline_run_id=pipeline_uuid,
                        crawl_result=result,
                    )
                    update_last_crawl_at(session, app.app_id)
                    if result.halted:
                        mark_pipeline_failed(
                            session,
                            pipeline_uuid,
                            error_message=result.halt_reason or "Crawl halted",
                        )
                    else:
                        mark_pipeline_completed(
                            session,
                            pipeline_uuid,
                            page_count=persist_result.page_count,
                            element_count=persist_result.element_count,
                        )
                except Exception as exc:
                    logger.exception(
                        "DiscoveryWorker persistence failed",
                        extra={"applicationId": application_id, "pipelineRunId": pipeline_run_id},
                    )
                    mark_pipeline_failed(session, pipeline_uuid, error_message=str(exc))
                    raise
            elif persist_enabled and pipeline_uuid is not None and result.halted:
                mark_pipeline_failed(
                    session,
                    pipeline_uuid,
                    error_message=result.halt_reason or "Crawl halted",
                )

            return result
    finally:
        if owns_session:
            session.close()


def fetch_application_homepage(
    application_id: str,
    *,
    pipeline_run_id: str | None = None,
    persist: bool = False,
    db: Session | None = None,
) -> PageSnapshot:
    """Fetch only the application base_url (Day 15 compatibility)."""
    result = crawl_application(
        application_id,
        crawl_overrides={"max_depth": 0, "max_pages": 1},
        pipeline_run_id=pipeline_run_id,
        persist=persist,
        db=db,
    )
    if result.halted:
        raise RuntimeError(result.halt_reason or "Crawl halted before homepage fetch")
    if not result.pages:
        raise RuntimeError(f"No pages fetched for application {application_id}")
    return result.pages[0]
