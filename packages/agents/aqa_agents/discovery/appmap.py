"""AppMap persistence — flows, JSON artifact, DB reads (Day 20)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from aqa_agents.discovery.flows import build_flows_from_pages
from aqa_shared.db.models import (
    Application,
    Artifact,
    ArtifactType,
    Element,
    Flow,
    FlowSource,
    Page,
    PipelineRun,
)
from aqa_shared.db.session import get_session_factory

logger = logging.getLogger(__name__)

DEFAULT_ARTIFACT_ROOT = "./artifacts"


@dataclass(frozen=True)
class AppMapBuildResult:
    page_count: int
    element_count: int
    flow_count: int
    appmap_path: str
    appmap_hash: str
    flows: list[dict]
    pages: list[dict]
    elements: list[dict]


def artifact_storage_root() -> Path:
    return Path(os.getenv("ARTIFACT_STORAGE_PATH", DEFAULT_ARTIFACT_ROOT)).resolve()


def appmap_artifact_path(pipeline_run_id: uuid.UUID) -> Path:
    return artifact_storage_root() / "appmaps" / f"{pipeline_run_id}.json"


def _compute_appmap_hash(pages: list[dict], flows: list[dict], element_count: int) -> str:
    payload = {
        "pages": sorted((p.get("url") or "" for p in pages)),
        "flows": sorted((f.get("name") or "" for f in flows)),
        "element_count": element_count,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return digest


def _load_appmap_records(session: Session, app_id: uuid.UUID) -> tuple[list[Page], list[Element]]:
    pages = list(session.scalars(select(Page).where(Page.app_id == app_id).order_by(Page.url)).all())
    elements = list(
        session.scalars(
            select(Element).join(Page).where(Page.app_id == app_id).order_by(Element.page_id)
        ).all()
    )
    return pages, elements


def _serialize_pages(pages: list[Page]) -> list[dict]:
    return [
        {
            "page_id": str(page.page_id),
            "url": page.url,
            "title": page.title,
            "screenshot_path": page.screenshot_path,
        }
        for page in pages
    ]


def _serialize_elements(elements: list[Element]) -> list[dict]:
    return [
        {
            "element_id": str(element.element_id),
            "page_id": str(element.page_id),
            "tag_name": element.tag_name,
            "role": element.role,
            "semantic_selector": element.semantic_selector,
            "xpath_fallback": element.xpath_fallback,
            "text_content": element.text_content,
        }
        for element in elements
    ]


def _replace_crawler_flows(session: Session, app_id: uuid.UUID, flow_defs: list[dict]) -> list[Flow]:
    session.execute(
        delete(Flow).where(Flow.app_id == app_id, Flow.source == FlowSource.crawler)
    )
    persisted: list[Flow] = []
    for item in flow_defs:
        flow = Flow(
            app_id=app_id,
            name=item["name"],
            description=item.get("description"),
            sequence=item.get("steps") or [],
            source=FlowSource.crawler,
        )
        session.add(flow)
        persisted.append(flow)
    session.flush()
    return persisted


def _register_appmap_artifact(
    session: Session,
    *,
    pipeline_run_id: uuid.UUID,
    path: Path,
) -> None:
    existing = session.scalars(
        select(Artifact).where(
            Artifact.pipeline_run_id == pipeline_run_id,
            Artifact.type == ArtifactType.appmap,
            Artifact.path == str(path),
        )
    ).first()
    if existing is not None:
        return
    session.add(
        Artifact(
            pipeline_run_id=pipeline_run_id,
            type=ArtifactType.appmap,
            path=str(path),
            size_bytes=path.stat().st_size,
        )
    )


def build_appmap_document(
    *,
    application_id: uuid.UUID,
    last_crawl_at: datetime | None,
    pages: list[dict],
    elements: list[dict],
    flows: list[dict],
) -> dict:
    return {
        "application_id": str(application_id),
        "last_crawl_at": last_crawl_at.isoformat() if last_crawl_at else None,
        "pages": pages,
        "elements": elements,
        "flows": [
            {
                "flow_id": flow.get("flow_id"),
                "name": flow.get("name"),
                "description": flow.get("description"),
                "source": flow.get("source"),
                "steps": flow.get("steps") or flow.get("sequence") or [],
            }
            for flow in flows
        ],
        "stats": {
            "page_count": len(pages),
            "element_count": len(elements),
            "flow_count": len(flows),
        },
    }


def build_and_persist_appmap(
    *,
    application_id: uuid.UUID,
    pipeline_run_id: uuid.UUID,
    db: Session | None = None,
) -> AppMapBuildResult:
    """Load crawl results, build flows, write AppMap JSON artifact, persist flows."""
    owns_session = db is None
    session = db or get_session_factory()()
    try:
        app = session.get(Application, application_id)
        if app is None:
            raise ValueError(f"Application not found: {application_id}")

        pages_orm, elements_orm = _load_appmap_records(session, application_id)
        page_dicts = _serialize_pages(pages_orm)
        element_dicts = _serialize_elements(elements_orm)
        flow_defs = build_flows_from_pages(page_dicts)

        persisted_flows = _replace_crawler_flows(session, application_id, flow_defs)
        flow_output = [
            {
                "flow_id": str(flow.flow_id),
                "name": flow.name,
                "description": flow.description,
                "source": flow.source.value,
                "steps": list(flow.sequence or []),
            }
            for flow in persisted_flows
        ]

        appmap_doc = build_appmap_document(
            application_id=application_id,
            last_crawl_at=app.last_crawl_at,
            pages=page_dicts,
            elements=element_dicts,
            flows=flow_output,
        )
        appmap_hash = _compute_appmap_hash(page_dicts, flow_output, len(element_dicts))

        dest = appmap_artifact_path(pipeline_run_id)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(appmap_doc, indent=2), encoding="utf-8")
        _register_appmap_artifact(session, pipeline_run_id=pipeline_run_id, path=dest)

        run = session.get(PipelineRun, pipeline_run_id)
        if run is not None:
            config = dict(run.config or {})
            config["appmap_hash"] = appmap_hash
            config["appmap_path"] = str(dest)
            config["discovery_stats"] = {
                "page_count": len(page_dicts),
                "element_count": len(element_dicts),
                "flow_count": len(flow_output),
            }
            run.config = config

        session.commit()
        logger.info(
            "DiscoveryAgent AppMap persisted",
            extra={
                "applicationId": str(application_id),
                "pipelineRunId": str(pipeline_run_id),
                "pageCount": len(page_dicts),
                "elementCount": len(element_dicts),
                "flowCount": len(flow_output),
            },
        )
        return AppMapBuildResult(
            page_count=len(page_dicts),
            element_count=len(element_dicts),
            flow_count=len(flow_output),
            appmap_path=str(dest),
            appmap_hash=appmap_hash,
            flows=flow_output,
            pages=page_dicts,
            elements=element_dicts,
        )
    except Exception:
        if owns_session:
            session.rollback()
        raise
    finally:
        if owns_session:
            session.close()


def load_appmap_for_application(session: Session, app_id: uuid.UUID) -> dict | None:
    """Build AppMap response from current DB state."""
    app = session.get(Application, app_id)
    if app is None:
        return None

    pages_orm, elements_orm = _load_appmap_records(session, app_id)
    flows_orm = list(
        session.scalars(select(Flow).where(Flow.app_id == app_id).order_by(Flow.name)).all()
    )
    page_dicts = _serialize_pages(pages_orm)
    element_dicts = _serialize_elements(elements_orm)
    flow_output = [
        {
            "flow_id": str(flow.flow_id),
            "name": flow.name,
            "description": flow.description,
            "source": flow.source.value,
            "steps": list(flow.sequence or []),
        }
        for flow in flows_orm
    ]
    return build_appmap_document(
        application_id=app_id,
        last_crawl_at=app.last_crawl_at,
        pages=page_dicts,
        elements=element_dicts,
        flows=flow_output,
    )
