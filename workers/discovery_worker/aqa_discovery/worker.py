"""Discovery worker orchestration helpers."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from aqa_discovery.auth import AuthError, load_auth_config, write_credential_audit
from aqa_discovery.auth_intelligence import collect_auth_signals_from_crawl
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
from aqa_shared.discovery.persona_merge import build_persona_visibility_artifact
from aqa_shared.db.models import Application, CredentialAuditAction
from aqa_shared.db.session import get_session_factory
from aqa_shared.sse import PipelineEventType, publish_pipeline_event

logger = logging.getLogger(__name__)

DISCOVERY_STAGE = "discover"


def _merge_crawl_results(results: list[CrawlResult]) -> CrawlResult:
    from aqa_discovery.network_capture import merge_api_endpoints

    if not results:
        return CrawlResult()
    if len(results) == 1:
        return results[0]

    merged = CrawlResult()
    seen_urls: set[str] = set()
    for result in results:
        for page in result.pages:
            if page.url in seen_urls:
                continue
            seen_urls.add(page.url)
            merged.pages.append(page)
        merged.api_endpoints = merge_api_endpoints(merged.api_endpoints, result.api_endpoints)
        merged.har_entries.extend(result.har_entries)
        merged.stats.pages_crawled = max(merged.stats.pages_crawled, result.stats.pages_crawled)
        merged.stats.states_discovered += result.stats.states_discovered
        merged.stats.interactions_executed += result.stats.interactions_executed
        merged.authenticated = merged.authenticated or result.authenticated
        if result.halted:
            merged.halted = True
            merged.halt_reason = merged.halt_reason or result.halt_reason
            merged.halt_url = merged.halt_url or result.halt_url
        for event in result.spa_route_events:
            key = (event.from_url, event.to_url, event.discovery_method)
            if key not in {(item.from_url, item.to_url, item.discovery_method) for item in merged.spa_route_events}:
                merged.spa_route_events.append(event)
    return merged


def _run_single_persona_crawl(
    *,
    app: Application,
    settings: CrawlSettings,
    start_urls: list[str],
    auth_config: dict,
    pipeline_run_id: str | None,
    live_progress: bool,
    persist_enabled: bool,
    persona_id: str | None,
    audit,
) -> CrawlResult:
    authenticated = False

    def _on_progress(_snapshot: PageSnapshot, stats) -> None:
        if pipeline_run_id:
            _publish_crawl_progress(
                pipeline_run_id,
                pages_discovered=stats.pages_crawled,
                max_pages=stats.max_pages,
                current_url=_snapshot.url,
                states_discovered=stats.states_discovered,
                interactions_executed=stats.interactions_executed,
            )
        if live_progress:
            states = len(_snapshot.states)
            discovered = len(_snapshot.discovered_urls)
            cic_tag = f" states={states}" if states else ""
            disc_tag = f" discovered={discovered}" if discovered else ""
            print(
                f"  [CIC] page {stats.pages_crawled}/{stats.max_pages} "
                f"depth={_snapshot.depth} "
                f"elements={len(_snapshot.elements)}{cic_tag}{disc_tag} "
                f"interactions={stats.interactions_executed} "
                f"| {(_snapshot.title or _snapshot.url)[:70]}",
                flush=True,
            )

    def _on_cic_progress(current_url: str, stats, extra: dict | None = None) -> None:
        if not pipeline_run_id:
            return
        meta = extra or {}
        _publish_crawl_progress(
            pipeline_run_id,
            pages_discovered=stats.pages_crawled,
            max_pages=stats.max_pages,
            current_url=current_url,
            states_discovered=stats.states_discovered,
            interactions_executed=stats.interactions_executed,
            discovered_url=meta.get("discovered_url"),
            view_label=meta.get("view_label"),
            phase=meta.get("phase"),
        )

    with CrawlSession(
        page_timeout_ms=settings.page_timeout_ms,
        headless=settings.headless,
        browser_channel=settings.browser_channel,
        user_agent=settings.user_agent,
        locale=settings.locale,
        viewport_width=settings.viewport_width,
        viewport_height=settings.viewport_height,
        app_id=app.app_id if persist_enabled else None,
        capture_artifacts=persist_enabled,
    ) as crawl:
        if auth_config:
            try:
                authenticated = crawl.authenticate(
                    auth_config=auth_config,
                    base_url=app.base_url,
                    audit=audit,
                )
            except AuthError as exc:
                logger.warning(
                    "DiscoveryWorker authentication failed",
                    extra={
                        "applicationId": str(app.app_id),
                        "personaId": persona_id,
                        "error": exc.message,
                    },
                )
                return CrawlResult(
                    halted=True,
                    halt_reason=exc.message,
                    authenticated=False,
                    auth_signals=collect_auth_signals_from_crawl(
                        pages=[],
                        api_endpoints=[],
                        authenticated=False,
                        persona_id=persona_id,
                        halt_reason=exc.message,
                    ),
                )

        result = crawl.crawl_bfs(
            start_urls,
            settings,
            on_progress=_on_progress if (pipeline_run_id or live_progress) else None,
            on_cic_progress=_on_cic_progress if pipeline_run_id else None,
        )
        result.authenticated = authenticated
        result.auth_signals = collect_auth_signals_from_crawl(
            pages=result.pages,
            api_endpoints=result.api_endpoints,
            authenticated=authenticated,
            persona_id=persona_id,
            halt_reason=result.halt_reason,
            halt_url=result.halt_url,
        )
        return result


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
    states_discovered: int = 0,
    interactions_executed: int = 0,
    discovered_url: str | None = None,
    view_label: str | None = None,
    phase: str | None = None,
) -> None:
    payload: dict = {
        "stage": DISCOVERY_STAGE,
        "pages_discovered": pages_discovered,
        "max_pages": max_pages,
        "current_url": current_url,
        "states_discovered": states_discovered,
        "interactions_executed": interactions_executed,
    }
    if discovered_url:
        payload["discovered_url"] = discovered_url
    if view_label:
        payload["view_label"] = view_label
    if phase:
        payload["phase"] = phase
    publish_pipeline_event(
        pipeline_run_id,
        PipelineEventType.stage_progress,
        payload,
    )


def crawl_application(
    application_id: str,
    *,
    crawl_overrides: dict | None = None,
    discover_config: dict | None = None,
    pipeline_run_id: str | None = None,
    persist: bool = True,
    live_progress: bool = False,
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
        discover = discover_config or {}
        network_keys = ("capture_network", "capture_har", "openapi_url", "excluded_analytics_domains")
        merged_overrides = {**(crawl_overrides or {})}
        for key in network_keys:
            if key in discover:
                merged_overrides[key] = discover[key]
        if not merged_overrides.get("openapi_url") and crawl_config.get("openapi_url"):
            merged_overrides["openapi_url"] = crawl_config.get("openapi_url")
        settings = CrawlSettings.from_crawl_config(app.base_url, crawl_config, overrides=merged_overrides)
        start_urls = _build_start_urls(app)

        def _audit(action: CredentialAuditAction) -> None:
            write_credential_audit(
                session,
                app_id=app.app_id,
                pipeline_run_id=pipeline_uuid,
                action=action,
            )

        stored_auth = app.auth_config if isinstance(app.auth_config, dict) else {}
        default_auth_config = load_auth_config(stored_auth, audit=_audit)
        personas = list(discover.get("personas") or [])
    except Exception:
        if owns_session:
            session.close()
        raise

    persist_result: PersistResult | None = None

    try:
        persona_results: list[dict] = []
        crawl_results: list[CrawlResult] = []

        if personas:
            per_persona_max = int(
                discover.get("per_persona_max_pages")
                or crawl_config.get("per_persona_max_pages")
                or settings.max_pages
            )
            for persona in personas:
                persona_id = str(persona.get("persona_id") or persona.get("personaId") or "").strip()
                if not persona_id:
                    continue
                persona_auth = persona.get("auth_config") or persona.get("authConfig") or {}
                persona_auth_config = (
                    load_auth_config(persona_auth, audit=_audit)
                    if persona_auth
                    else default_auth_config
                )
                persona_settings = CrawlSettings.from_crawl_config(
                    app.base_url,
                    crawl_config,
                    overrides={**merged_overrides, "max_pages": per_persona_max},
                )
                result = _run_single_persona_crawl(
                    app=app,
                    settings=persona_settings,
                    start_urls=start_urls,
                    auth_config=persona_auth_config,
                    pipeline_run_id=pipeline_run_id,
                    live_progress=live_progress,
                    persist_enabled=persist_enabled,
                    persona_id=persona_id,
                    audit=_audit,
                )
                crawl_results.append(result)
                persona_results.append(
                    {
                        "persona_id": persona_id,
                        "label": persona.get("label"),
                        "authenticated": result.authenticated,
                        "page_urls": [page.url for page in result.pages],
                        "halted": result.halted,
                    }
                )
                if result.halted and len(personas) == 1:
                    break
        else:
            crawl_results.append(
                _run_single_persona_crawl(
                    app=app,
                    settings=settings,
                    start_urls=start_urls,
                    auth_config=default_auth_config,
                    pipeline_run_id=pipeline_run_id,
                    live_progress=live_progress,
                    persist_enabled=persist_enabled,
                    persona_id=None,
                    audit=_audit,
                )
            )

        result = _merge_crawl_results(crawl_results)
        if persona_results:
            result.persona_visibility = build_persona_visibility_artifact(persona_results=persona_results)
        elif result.authenticated:
            result.persona_visibility = build_persona_visibility_artifact(
                persona_results=[
                    {
                        "persona_id": "default",
                        "label": "Default",
                        "authenticated": True,
                        "page_urls": [page.url for page in result.pages],
                    }
                ]
            )

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
                        state_count=persist_result.state_count,
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
