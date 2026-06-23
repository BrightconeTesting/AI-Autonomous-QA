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

from aqa_discovery.types import CrawlResult, FormSnapshot, PageSnapshot, UIStateSnapshot
from aqa_shared.db.models import (
    Application,
    Artifact,
    ArtifactType,
    ApiEndpoint,
    ApiUiMapping,
    Element,
    Form,
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
    db.execute(delete(Form).where(Form.page_id == page.page_id))
    db.flush()

    element_count = 0
    state_key_to_id: dict[str, uuid.UUID] = {}

    states = snapshot.states or []
    if not states:
        element_count, xpath_map = _replace_baseline_elements(db, page_id=page.page_id, snapshot=snapshot)
        _persist_forms(
            db,
            app_id=app_id,
            page_id=page.page_id,
            state_id=None,
            forms=snapshot.forms,
            xpath_to_element_id=xpath_map,
        )
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
        count, xpath_map = _replace_state_elements(
            db, page_id=page.page_id, state_id=state_row.state_id, state=state_snap
        )
        element_count += count
        _persist_forms(
            db,
            app_id=app_id,
            page_id=page.page_id,
            state_id=state_row.state_id,
            forms=state_snap.forms,
            xpath_to_element_id=xpath_map,
        )

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


def _replace_baseline_elements(
    db: Session, *, page_id: uuid.UUID, snapshot: PageSnapshot
) -> tuple[int, dict[str, uuid.UUID]]:
    db.execute(delete(Element).where(Element.page_id == page_id))
    xpath_map: dict[str, uuid.UUID] = {}
    count = 0
    for item in snapshot.elements:
        row = Element(
            page_id=page_id,
            tag_name=item.tag_name,
            role=item.role,
            text_content=item.text_content,
            semantic_selector=item.semantic_selector,
            xpath_fallback=item.xpath_fallback,
            attributes=item.attributes,
        )
        db.add(row)
        db.flush()
        if item.xpath_fallback:
            xpath_map[item.xpath_fallback] = row.element_id
        count += 1
    return count, xpath_map


def _replace_state_elements(
    db: Session,
    *,
    page_id: uuid.UUID,
    state_id: uuid.UUID,
    state: UIStateSnapshot,
) -> tuple[int, dict[str, uuid.UUID]]:
    xpath_map: dict[str, uuid.UUID] = {}
    count = 0
    for item in state.elements:
        row = Element(
            page_id=page_id,
            state_id=state_id,
            tag_name=item.tag_name,
            role=item.role,
            text_content=item.text_content,
            semantic_selector=item.semantic_selector,
            xpath_fallback=item.xpath_fallback,
            attributes=item.attributes,
        )
        db.add(row)
        db.flush()
        if item.xpath_fallback:
            xpath_map[item.xpath_fallback] = row.element_id
        count += 1
    return count, xpath_map


def _persist_forms(
    db: Session,
    *,
    app_id: uuid.UUID,
    page_id: uuid.UUID,
    state_id: uuid.UUID | None,
    forms: list[FormSnapshot],
    xpath_to_element_id: dict[str, uuid.UUID],
) -> None:
    seen_keys: set[str] = set()
    for form in forms:
        if form.form_key in seen_keys:
            continue
        seen_keys.add(form.form_key)
        field_ids = [
            str(xpath_to_element_id[xpath])
            for xpath in form.field_xpaths
            if xpath in xpath_to_element_id
        ]
        attrs = dict(form.attributes)
        attrs["form_key"] = form.form_key
        attrs["name"] = form.name
        db.add(
            Form(
                app_id=app_id,
                page_id=page_id,
                state_id=state_id,
                action=form.action,
                method=form.method,
                attributes=attrs,
                field_element_ids=field_ids,
            )
        )


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


def _persist_api_endpoints(
    db: Session,
    *,
    app_id: uuid.UUID,
    crawl_result: CrawlResult,
    page_by_url: dict[str, Page],
) -> int:
    db.execute(delete(ApiEndpoint).where(ApiEndpoint.app_id == app_id))
    rows: dict[str, dict] = {}

    for snapshot in crawl_result.pages:
        page = page_by_url.get(snapshot.url)
        if page is None:
            continue
        for endpoint in snapshot.api_endpoints:
            key = f"{endpoint.method.upper()} {endpoint.path_pattern}"
            row = rows.setdefault(
                key,
                {
                    "method": endpoint.method.upper(),
                    "path": endpoint.path,
                    "path_pattern": endpoint.path_pattern,
                    "source": endpoint.source,
                    "request_schema": dict(endpoint.request_schema),
                    "response_schema": dict(endpoint.response_schema),
                    "seen_count": 0,
                    "seen_page_ids": set(),
                    "first_seen_page_id": page.page_id,
                },
            )
            row["seen_count"] += endpoint.seen_count
            row["seen_page_ids"].add(str(page.page_id))

    for endpoint in crawl_result.api_endpoints:
        key = f"{endpoint.method.upper()} {endpoint.path_pattern}"
        existing = rows.get(key)
        if existing is not None:
            if endpoint.source in {"openapi", "both"}:
                if existing["source"] == "network" and endpoint.source == "openapi":
                    existing["source"] = "both"
                elif endpoint.source == "both":
                    existing["source"] = "both"
                if endpoint.request_schema:
                    existing["request_schema"] = dict(endpoint.request_schema)
                if endpoint.response_schema:
                    existing["response_schema"] = dict(endpoint.response_schema)
            continue
        rows[key] = {
            "method": endpoint.method.upper(),
            "path": endpoint.path,
            "path_pattern": endpoint.path_pattern,
            "source": endpoint.source,
            "request_schema": dict(endpoint.request_schema),
            "response_schema": dict(endpoint.response_schema),
            "seen_count": endpoint.seen_count,
            "seen_page_ids": set(),
            "first_seen_page_id": None,
        }

    for row in rows.values():
        db.add(
            ApiEndpoint(
                app_id=app_id,
                method=row["method"],
                path=row["path"],
                path_pattern=row["path_pattern"],
                source=row["source"],
                request_schema=row["request_schema"],
                response_schema=row["response_schema"],
                first_seen_page_id=row["first_seen_page_id"],
                seen_page_ids=sorted(row["seen_page_ids"]),
                seen_count=max(1, row["seen_count"]),
            )
        )
    return len(rows)


def _persist_api_ui_mappings(
    db: Session,
    *,
    app_id: uuid.UUID,
    crawl_result: CrawlResult,
    page_by_url: dict[str, Page],
) -> int:
    from aqa_shared.discovery.api_ui_mapper import build_api_ui_mappings

    pages = list(db.scalars(select(Page).where(Page.app_id == app_id)).all())
    page_dicts = [
        {"page_id": str(page.page_id), "url": page.url, "title": page.title} for page in pages
    ]
    forms = list(db.scalars(select(Form).where(Form.app_id == app_id)).all())
    form_dicts = [
        {
            "form_id": str(form.form_id),
            "page_id": str(form.page_id),
            "method": str(form.method or "get").lower(),
            "attributes": dict(form.attributes or {}),
            "field_element_ids": [str(item) for item in (form.field_element_ids or [])],
        }
        for form in forms
    ]
    elements = list(
        db.scalars(select(Element).join(Page).where(Page.app_id == app_id)).all()
    )
    element_dicts = [
        {
            "element_id": str(element.element_id),
            "page_id": str(element.page_id),
            "text_content": element.text_content,
            "attributes": dict(element.attributes or {}),
            "form_id": str((element.attributes or {}).get("form_id") or ""),
        }
        for element in elements
    ]
    endpoints = list(db.scalars(select(ApiEndpoint).where(ApiEndpoint.app_id == app_id)).all())
    body_keys_by_pattern: dict[str, list[str]] = {}
    for snapshot in crawl_result.pages:
        for endpoint in snapshot.api_endpoints:
            if not endpoint.body_keys:
                continue
            key = f"{endpoint.method.upper()} {endpoint.path_pattern}"
            body_keys_by_pattern.setdefault(key, []).extend(endpoint.body_keys)

    api_endpoint_dicts: list[dict] = []
    for endpoint in endpoints:
        method = str(endpoint.method or "GET").upper()
        key = f"{method} {endpoint.path_pattern}"
        seen_ids = [str(page_id) for page_id in (endpoint.seen_page_ids or [])]
        api_endpoint_dicts.append(
            {
                "endpoint_id": str(endpoint.endpoint_id),
                "method": method,
                "path": endpoint.path,
                "path_pattern": endpoint.path_pattern,
                "source": endpoint.source,
                "request_schema": dict(endpoint.request_schema or {}),
                "seen_on_page_ids": seen_ids,
                "first_seen_page_id": str(endpoint.first_seen_page_id) if endpoint.first_seen_page_id else None,
                "body_keys": list(dict.fromkeys(body_keys_by_pattern.get(key, []))),
            }
        )

    interaction_events_by_page: dict[str, list[dict]] = {}
    network_events_by_page: dict[str, list[dict]] = {}
    for snapshot in crawl_result.pages:
        page = page_by_url.get(snapshot.url)
        if page is None:
            continue
        page_id = str(page.page_id)
        interaction_events_by_page[page_id] = [
            event.model_dump() for event in snapshot.interaction_events
        ]
        network_events_by_page[page_id] = [
            event.model_dump() for event in snapshot.network_events
        ]

    mappings = build_api_ui_mappings(
        pages=page_dicts,
        forms=form_dicts,
        elements=element_dicts,
        api_endpoints=api_endpoint_dicts,
        interaction_events_by_page=interaction_events_by_page,
        network_events_by_page=network_events_by_page,
    )

    db.execute(delete(ApiUiMapping).where(ApiUiMapping.app_id == app_id))
    valid_endpoint_ids = {str(endpoint.endpoint_id) for endpoint in endpoints}
    valid_page_ids = {str(page.page_id) for page in pages}
    inserted = 0
    for mapping in mappings:
        endpoint_id = str(mapping.get("api_endpoint_id") or "")
        page_id = str(mapping.get("page_id") or "")
        if endpoint_id not in valid_endpoint_ids or page_id not in valid_page_ids:
            continue
        db.add(
            ApiUiMapping(
                app_id=app_id,
                api_endpoint_id=uuid.UUID(endpoint_id),
                page_id=uuid.UUID(page_id),
                form_id=uuid.UUID(str(mapping["form_id"])) if mapping.get("form_id") else None,
                element_id=uuid.UUID(str(mapping["element_id"])) if mapping.get("element_id") else None,
                flow_id=uuid.UUID(str(mapping["flow_id"])) if mapping.get("flow_id") else None,
                trigger_action=dict(mapping.get("trigger_action") or {}),
                confidence=float(mapping.get("confidence") or 0),
                correlation_method=str(mapping.get("correlation_method") or "heuristic"),
                review_required=bool(mapping.get("review_required")),
            )
        )
        inserted += 1
    return inserted


def _register_har_artifact(
    db: Session,
    *,
    pipeline_run_id: uuid.UUID,
    app_id: uuid.UUID,
    har_entries: list[dict],
) -> str | None:
    if not har_entries:
        return None
    import json

    dest = artifact_storage_root() / "har" / str(app_id) / f"{pipeline_run_id}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"log": {"entries": har_entries}}, indent=2), encoding="utf-8")

    existing = db.scalars(
        select(Artifact).where(
            Artifact.pipeline_run_id == pipeline_run_id,
            Artifact.type == ArtifactType.report,
            Artifact.path == str(dest),
        )
    ).first()
    if existing is None:
        db.add(
            Artifact(
                pipeline_run_id=pipeline_run_id,
                type=ArtifactType.report,
                path=str(dest),
                size_bytes=dest.stat().st_size,
            )
        )
    return str(dest)


def _register_network_timeline_artifact(
    db: Session,
    *,
    pipeline_run_id: uuid.UUID,
    app_id: uuid.UUID,
    crawl_result: CrawlResult,
    page_by_url: dict[str, Page],
) -> str | None:
    import json

    events_by_page: dict[str, list[dict]] = {}
    for snapshot in crawl_result.pages:
        page = page_by_url.get(snapshot.url)
        if page is None or not snapshot.network_events:
            continue
        events_by_page[str(page.page_id)] = [event.model_dump() for event in snapshot.network_events]
    if not events_by_page:
        return None

    dest = artifact_storage_root() / "network_timeline" / str(app_id) / f"{pipeline_run_id}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"events_by_page": events_by_page}, indent=2), encoding="utf-8")

    existing = db.scalars(
        select(Artifact).where(
            Artifact.pipeline_run_id == pipeline_run_id,
            Artifact.type == ArtifactType.report,
            Artifact.path == str(dest),
        )
    ).first()
    if existing is None:
        db.add(
            Artifact(
                pipeline_run_id=pipeline_run_id,
                type=ArtifactType.report,
                path=str(dest),
                size_bytes=dest.stat().st_size,
            )
        )
    return str(dest)


def _register_auth_signals_artifact(
    db: Session,
    *,
    pipeline_run_id: uuid.UUID,
    app_id: uuid.UUID,
    auth_signals: dict,
) -> str | None:
    import json

    if not auth_signals:
        return None
    dest = artifact_storage_root() / "auth_signals" / str(app_id) / f"{pipeline_run_id}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(auth_signals, indent=2), encoding="utf-8")
    existing = db.scalars(
        select(Artifact).where(
            Artifact.pipeline_run_id == pipeline_run_id,
            Artifact.type == ArtifactType.report,
            Artifact.path == str(dest),
        )
    ).first()
    if existing is None:
        db.add(
            Artifact(
                pipeline_run_id=pipeline_run_id,
                type=ArtifactType.report,
                path=str(dest),
                size_bytes=dest.stat().st_size,
            )
        )
    return str(dest)


def _register_persona_visibility_artifact(
    db: Session,
    *,
    pipeline_run_id: uuid.UUID,
    app_id: uuid.UUID,
    persona_visibility: dict,
    page_by_url: dict[str, Page],
) -> str | None:
    import json

    if not persona_visibility:
        return None
    payload = dict(persona_visibility)
    payload["pages"] = [
        {"page_id": str(page.page_id), "url": page.url} for page in page_by_url.values()
    ]
    dest = artifact_storage_root() / "persona_visibility" / str(app_id) / f"{pipeline_run_id}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    existing = db.scalars(
        select(Artifact).where(
            Artifact.pipeline_run_id == pipeline_run_id,
            Artifact.type == ArtifactType.report,
            Artifact.path == str(dest),
        )
    ).first()
    if existing is None:
        db.add(
            Artifact(
                pipeline_run_id=pipeline_run_id,
                type=ArtifactType.report,
                path=str(dest),
                size_bytes=dest.stat().st_size,
            )
        )
    return str(dest)


def _register_spa_routes_artifact(
    db: Session,
    *,
    pipeline_run_id: uuid.UUID,
    app_id: uuid.UUID,
    spa_route_events: list,
) -> str | None:
    import json

    if not spa_route_events:
        return None
    payload = {
        "events": [
            event.model_dump() if hasattr(event, "model_dump") else dict(event)
            for event in spa_route_events
        ]
    }
    dest = artifact_storage_root() / "spa_routes" / str(app_id) / f"{pipeline_run_id}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    existing = db.scalars(
        select(Artifact).where(
            Artifact.pipeline_run_id == pipeline_run_id,
            Artifact.type == ArtifactType.report,
            Artifact.path == str(dest),
        )
    ).first()
    if existing is None:
        db.add(
            Artifact(
                pipeline_run_id=pipeline_run_id,
                type=ArtifactType.report,
                path=str(dest),
                size_bytes=dest.stat().st_size,
            )
        )
    return str(dest)


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
    page_by_url: dict[str, Page] = {}

    for snapshot in crawl_result.pages:
        page = _upsert_page(db, app_id=app_id, snapshot=snapshot)
        page_by_url[snapshot.url] = page
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

    endpoint_count = _persist_api_endpoints(
        db,
        app_id=app_id,
        crawl_result=crawl_result,
        page_by_url=page_by_url,
    )
    db.flush()
    mapping_count = _persist_api_ui_mappings(
        db,
        app_id=app_id,
        crawl_result=crawl_result,
        page_by_url=page_by_url,
    )
    if crawl_result.har_entries:
        har_path = _register_har_artifact(
            db,
            pipeline_run_id=pipeline_run_id,
            app_id=app_id,
            har_entries=crawl_result.har_entries,
        )
        if har_path:
            artifact_count += 1

    timeline_path = _register_network_timeline_artifact(
        db,
        pipeline_run_id=pipeline_run_id,
        app_id=app_id,
        crawl_result=crawl_result,
        page_by_url=page_by_url,
    )
    if timeline_path:
        artifact_count += 1

    if crawl_result.auth_signals:
        auth_path = _register_auth_signals_artifact(
            db,
            pipeline_run_id=pipeline_run_id,
            app_id=app_id,
            auth_signals=crawl_result.auth_signals,
        )
        if auth_path:
            artifact_count += 1
    if crawl_result.persona_visibility:
        persona_path = _register_persona_visibility_artifact(
            db,
            pipeline_run_id=pipeline_run_id,
            app_id=app_id,
            persona_visibility=crawl_result.persona_visibility,
            page_by_url=page_by_url,
        )
        if persona_path:
            artifact_count += 1
    if crawl_result.spa_route_events:
        spa_path = _register_spa_routes_artifact(
            db,
            pipeline_run_id=pipeline_run_id,
            app_id=app_id,
            spa_route_events=crawl_result.spa_route_events,
        )
        if spa_path:
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
            "endpointCount": endpoint_count,
            "mappingCount": mapping_count,
            "artifactCount": artifact_count,
        },
    )
    return PersistResult(
        page_count=page_count,
        element_count=element_count,
        state_count=state_count,
        artifact_count=artifact_count,
    )
