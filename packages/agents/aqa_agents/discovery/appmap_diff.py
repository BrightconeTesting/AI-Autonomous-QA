"""Deterministic AppMap diff between pipeline runs (DISCOVERY-AGENT-VISION-SPEC §9.9)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from aqa_agents.discovery.appmap import appmap_artifact_path
from aqa_shared.db.models import PipelineRun, PipelineStage, PipelineStatus


class AppMapDiffError(Exception):
    """Raised when diff inputs are invalid or artifacts are missing."""


def load_appmap_artifact(
    session: Session,
    *,
    app_id: uuid.UUID,
    pipeline_run_id: uuid.UUID,
) -> dict[str, Any]:
    """Load immutable AppMap JSON for a completed discover pipeline run."""
    run = session.get(PipelineRun, pipeline_run_id)
    if run is None or run.application_id != app_id:
        raise AppMapDiffError(f"No pipeline run {pipeline_run_id} for application {app_id}")
    if run.current_stage != PipelineStage.discover:
        raise AppMapDiffError(f"Pipeline run {pipeline_run_id} is not a discover run")

    config = dict(run.config or {})
    configured_path = config.get("appmap_path")
    candidates: list[Path] = []
    if configured_path:
        candidates.append(Path(str(configured_path)))
    candidates.append(appmap_artifact_path(pipeline_run_id))

    for path in candidates:
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
            raise AppMapDiffError(f"AppMap artifact at {path} is not a JSON object")

    raise AppMapDiffError(f"No AppMap artifact found for pipeline run {pipeline_run_id}")


def list_discover_runs(
    session: Session,
    app_id: uuid.UUID,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Summarize completed discover runs that have (or may have) AppMap artifacts."""
    runs = list(
        session.scalars(
            select(PipelineRun)
            .where(
                PipelineRun.application_id == app_id,
                PipelineRun.current_stage == PipelineStage.discover,
                PipelineRun.status == PipelineStatus.completed,
            )
            .order_by(PipelineRun.started_at.desc())
            .limit(limit)
        ).all()
    )
    summaries: list[dict[str, Any]] = []
    for run in runs:
        config = dict(run.config or {})
        stats = dict(config.get("discovery_stats") or {})
        path = Path(str(config.get("appmap_path") or appmap_artifact_path(run.id)))
        summaries.append(
            {
                "pipeline_run_id": str(run.id),
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "ended_at": run.ended_at.isoformat() if run.ended_at else None,
                "appmap_hash": config.get("appmap_hash"),
                "has_artifact": path.exists(),
                "page_count": stats.get("page_count"),
                "element_count": stats.get("element_count"),
                "flow_count": stats.get("flow_count"),
            }
        )
    return summaries


def _index_by(items: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in items:
        value = str(item.get(key) or "").strip()
        if value:
            indexed[value] = item
    return indexed


def _api_key(endpoint: dict[str, Any]) -> str:
    method = str(endpoint.get("method") or "GET").upper()
    path = str(endpoint.get("path_pattern") or endpoint.get("path") or "")
    endpoint_id = str(endpoint.get("endpoint_id") or "")
    return f"{method}:{path}" if path else endpoint_id


def _dependency_edge_key(edge: dict[str, Any]) -> str:
    return "|".join(
        [
            str(edge.get("from_endpoint_id") or ""),
            str(edge.get("to_endpoint_id") or ""),
            str(edge.get("edge_type") or ""),
        ]
    )


def _page_metadata(page: dict[str, Any]) -> dict[str, Any]:
    return {
        "page_id": str(page.get("page_id") or ""),
        "url": str(page.get("url") or ""),
        "title": page.get("title"),
    }


def _module_snapshot(module: dict[str, Any]) -> dict[str, Any]:
    return {
        "module_id": str(module.get("module_id") or ""),
        "name": str(module.get("name") or ""),
        "parent_module_id": module.get("parent_module_id"),
        "pages": sorted(str(item) for item in (module.get("pages") or [])),
        "flow_ids": sorted(str(item) for item in (module.get("flow_ids") or [])),
        "risk_score": module.get("risk_score"),
        "testability_score": module.get("testability_score"),
        "automation_complexity_score": module.get("automation_complexity_score"),
    }


def _entity_snapshot(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "entity_id": str(entity.get("entity_id") or ""),
        "name": str(entity.get("name") or ""),
        "module_id": entity.get("module_id"),
        "crud_surfaces": entity.get("crud_surfaces") or {},
    }


def _score_delta(name: str, from_doc: dict[str, Any], to_doc: dict[str, Any]) -> dict[str, Any] | None:
    from_summary = from_doc.get("scoring_summary") if isinstance(from_doc.get("scoring_summary"), dict) else {}
    to_summary = to_doc.get("scoring_summary") if isinstance(to_doc.get("scoring_summary"), dict) else {}
    from_val = from_doc.get(name, from_summary.get(name))
    to_val = to_doc.get(name, to_summary.get(name))
    if from_val is None and to_val is None:
        return None
    try:
        from_int = int(from_val or 0)
        to_int = int(to_val or 0)
    except (TypeError, ValueError):
        return None
    return {"from": from_int, "to": to_int, "delta": to_int - from_int}


def compute_appmap_diff(from_doc: dict[str, Any], to_doc: dict[str, Any]) -> dict[str, Any]:
    """Compare normalized AppMap subsets between two artifact documents."""
    from_pages = list(from_doc.get("pages") or [])
    to_pages = list(to_doc.get("pages") or [])
    from_pages_by_id = _index_by(from_pages, "page_id")
    to_pages_by_id = _index_by(to_pages, "page_id")

    added_pages = [
        _page_metadata(page)
        for page_id, page in to_pages_by_id.items()
        if page_id not in from_pages_by_id
    ]
    removed_pages = [
        _page_metadata(page)
        for page_id, page in from_pages_by_id.items()
        if page_id not in to_pages_by_id
    ]
    changed_pages: list[dict[str, Any]] = []
    for page_id, to_page in to_pages_by_id.items():
        from_page = from_pages_by_id.get(page_id)
        if from_page is None:
            continue
        fields: list[str] = []
        if str(from_page.get("url") or "") != str(to_page.get("url") or ""):
            fields.append("url")
        if (from_page.get("title") or "") != (to_page.get("title") or ""):
            fields.append("title")
        if fields:
            changed_pages.append({**_page_metadata(to_page), "changed_fields": fields})

    def _element_counts(pages: list[dict[str, Any]], elements: list[dict[str, Any]]) -> dict[str, int]:
        page_ids = {str(page.get("page_id") or "") for page in pages}
        counts = {page_id: 0 for page_id in page_ids}
        for element in elements:
            page_id = str(element.get("page_id") or "")
            if page_id in counts:
                counts[page_id] += 1
        return counts

    from_element_counts = _element_counts(from_pages, list(from_doc.get("elements") or []))
    to_element_counts = _element_counts(to_pages, list(to_doc.get("elements") or []))
    element_delta: list[dict[str, Any]] = []
    for page_id in sorted(set(from_element_counts) | set(to_element_counts)):
        from_count = from_element_counts.get(page_id, 0)
        to_count = to_element_counts.get(page_id, 0)
        if from_count == to_count:
            continue
        element_delta.append(
            {
                "page_id": page_id,
                "from_count": from_count,
                "to_count": to_count,
                "delta": to_count - from_count,
            }
        )

    from_apis = {_api_key(item): item for item in (from_doc.get("api_endpoints") or [])}
    to_apis = {_api_key(item): item for item in (to_doc.get("api_endpoints") or [])}
    added_apis = [
        {
            "endpoint_id": str(item.get("endpoint_id") or ""),
            "method": str(item.get("method") or "GET"),
            "path": str(item.get("path_pattern") or item.get("path") or ""),
        }
        for key, item in to_apis.items()
        if key not in from_apis
    ]
    removed_apis = [
        {
            "endpoint_id": str(item.get("endpoint_id") or ""),
            "method": str(item.get("method") or "GET"),
            "path": str(item.get("path_pattern") or item.get("path") or ""),
        }
        for key, item in from_apis.items()
        if key not in to_apis
    ]

    from_graph = from_doc.get("api_dependency_graph") if isinstance(from_doc.get("api_dependency_graph"), dict) else {}
    to_graph = to_doc.get("api_dependency_graph") if isinstance(to_doc.get("api_dependency_graph"), dict) else {}
    from_edges = {_dependency_edge_key(edge): edge for edge in (from_graph.get("edges") or [])}
    to_edges = {_dependency_edge_key(edge): edge for edge in (to_graph.get("edges") or [])}
    edges_added = list(to_edges[key] for key in to_edges if key not in from_edges)
    edges_removed = list(from_edges[key] for key in from_edges if key not in to_edges)

    from_modules = _index_by(list(from_doc.get("modules") or []), "module_id")
    to_modules = _index_by(list(to_doc.get("modules") or []), "module_id")
    modules_added = [_module_snapshot(to_modules[mid]) for mid in to_modules if mid not in from_modules]
    modules_removed = [_module_snapshot(from_modules[mid]) for mid in from_modules if mid not in to_modules]
    modules_changed: list[dict[str, Any]] = []
    for module_id, to_module in to_modules.items():
        from_module = from_modules.get(module_id)
        if from_module is None:
            continue
        from_snap = _module_snapshot(from_module)
        to_snap = _module_snapshot(to_module)
        changed_fields = [field for field in from_snap if from_snap.get(field) != to_snap.get(field)]
        if changed_fields:
            modules_changed.append(
                {
                    "module_id": module_id,
                    "name": to_snap["name"],
                    "changed_fields": changed_fields,
                    "from": from_snap,
                    "to": to_snap,
                }
            )

    from_entities = _index_by(list(from_doc.get("data_entities") or []), "entity_id")
    to_entities = _index_by(list(to_doc.get("data_entities") or []), "entity_id")
    entities_added = [_entity_snapshot(to_entities[eid]) for eid in to_entities if eid not in from_entities]
    entities_removed = [_entity_snapshot(from_entities[eid]) for eid in from_entities if eid not in to_entities]
    crud_changed: list[dict[str, Any]] = []
    for entity_id, to_entity in to_entities.items():
        from_entity = from_entities.get(entity_id)
        if from_entity is None:
            continue
        from_crud = from_entity.get("crud_surfaces") or {}
        to_crud = to_entity.get("crud_surfaces") or {}
        if from_crud != to_crud:
            crud_changed.append(
                {
                    "entity_id": entity_id,
                    "name": str(to_entity.get("name") or entity_id),
                    "from_crud_surfaces": from_crud,
                    "to_crud_surfaces": to_crud,
                }
            )

    score_fields = [
        "discovery_completeness_score",
        "app_risk_score",
        "app_testability_score",
        "app_automation_complexity_score",
    ]
    scores: dict[str, Any] = {}
    for field in score_fields:
        delta = _score_delta(field, from_doc, to_doc)
        if delta is not None:
            scores[field] = delta

    from_areas = {
        str(area.get("area_id") or ""): area for area in (from_doc.get("recommended_test_areas") or [])
    }
    to_areas = {
        str(area.get("area_id") or ""): area for area in (to_doc.get("recommended_test_areas") or [])
    }
    areas_added = [
        {
            "area_id": area_id,
            "area": area.get("area"),
            "priority_index": area.get("priority_index"),
            "area_type": area.get("area_type"),
        }
        for area_id, area in to_areas.items()
        if area_id not in from_areas
    ]
    areas_removed = [
        {
            "area_id": area_id,
            "area": area.get("area"),
            "priority_index": area.get("priority_index"),
            "area_type": area.get("area_type"),
        }
        for area_id, area in from_areas.items()
        if area_id not in to_areas
    ]

    unchanged = not any(
        [
            added_pages,
            removed_pages,
            changed_pages,
            element_delta,
            added_apis,
            removed_apis,
            edges_added,
            edges_removed,
            modules_added,
            modules_removed,
            modules_changed,
            entities_added,
            entities_removed,
            crud_changed,
            scores,
            areas_added,
            areas_removed,
        ]
    )

    return {
        "unchanged": unchanged,
        "pages": {
            "added": added_pages,
            "removed": removed_pages,
            "changed": changed_pages,
        },
        "elements": {"delta_by_page": element_delta},
        "api_endpoints": {"added": added_apis, "removed": removed_apis},
        "api_dependency_graph": {"edges_added": edges_added, "edges_removed": edges_removed},
        "modules": {
            "added": modules_added,
            "removed": modules_removed,
            "changed": modules_changed,
        },
        "scores": scores,
        "entities": {
            "added": entities_added,
            "removed": entities_removed,
            "crud_surfaces_changed": crud_changed,
        },
        "recommended_test_areas": {"added": areas_added, "removed": areas_removed},
    }


def diff_appmap_runs(
    session: Session,
    *,
    app_id: uuid.UUID,
    from_run_id: uuid.UUID,
    to_run_id: uuid.UUID,
) -> dict[str, Any]:
    if from_run_id == to_run_id:
        raise AppMapDiffError("from_run and to_run must be different pipeline runs")

    from_doc = load_appmap_artifact(session, app_id=app_id, pipeline_run_id=from_run_id)
    to_doc = load_appmap_artifact(session, app_id=app_id, pipeline_run_id=to_run_id)
    from_run = session.get(PipelineRun, from_run_id)
    to_run = session.get(PipelineRun, to_run_id)
    assert from_run is not None and to_run is not None

    diff = compute_appmap_diff(from_doc, to_doc)
    return {
        "application_id": str(app_id),
        "from_run_id": str(from_run_id),
        "to_run_id": str(to_run_id),
        "from_appmap_hash": dict(from_run.config or {}).get("appmap_hash"),
        "to_appmap_hash": dict(to_run.config or {}).get("appmap_hash"),
        **diff,
    }
