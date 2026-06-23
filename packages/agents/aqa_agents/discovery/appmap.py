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

from aqa_agents.discovery.flows import build_flows_from_pages, build_flows_from_states
from aqa_shared.db.models import (
    Application,
    Artifact,
    ArtifactType,
    ApiEndpoint,
    ApiUiMapping,
    Element,
    Flow,
    FlowSource,
    Form,
    Page,
    PageDiscovery,
    PageState,
    PipelineRun,
    StateTransition as StateTransitionRow,
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
    tokens_used: int = 0
    cost_estimate: float = 0.0
    llm_skip_reason: str | None = None


def artifact_storage_root() -> Path:
    return Path(os.getenv("ARTIFACT_STORAGE_PATH", DEFAULT_ARTIFACT_ROOT)).resolve()


def network_timeline_path(app_id: uuid.UUID, pipeline_run_id: uuid.UUID) -> Path:
    return artifact_storage_root() / "network_timeline" / str(app_id) / f"{pipeline_run_id}.json"


def load_network_timeline(
    session: Session,
    *,
    app_id: uuid.UUID,
    pipeline_run_id: uuid.UUID | None = None,
) -> dict[str, list[dict]]:
    """Load per-page network events for dependency graph inference."""
    if pipeline_run_id is not None:
        path = network_timeline_path(app_id, pipeline_run_id)
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            events = payload.get("events_by_page") or {}
            return events if isinstance(events, dict) else {}

    row = session.scalars(
        select(Artifact)
        .join(PipelineRun, Artifact.pipeline_run_id == PipelineRun.id)
        .where(
            PipelineRun.application_id == app_id,
            Artifact.path.like(f"%network_timeline/{app_id}/%"),
        )
        .order_by(Artifact.created_at.desc())
        .limit(1)
    ).first()
    if row is None:
        return {}
    path = Path(row.path)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    events = payload.get("events_by_page") or {}
    return events if isinstance(events, dict) else {}


def _load_latest_artifact_json(
    session: Session,
    *,
    app_id: uuid.UUID,
    pipeline_run_id: uuid.UUID | None,
    path_fragment: str,
    direct_path: Path | None = None,
) -> dict:
    if pipeline_run_id is not None and direct_path is not None and direct_path.exists():
        payload = json.loads(direct_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    row = session.scalars(
        select(Artifact)
        .join(PipelineRun, Artifact.pipeline_run_id == PipelineRun.id)
        .where(
            PipelineRun.application_id == app_id,
            Artifact.path.like(f"%{path_fragment}/{app_id}/%"),
        )
        .order_by(Artifact.created_at.desc())
        .limit(1)
    ).first()
    if row is None:
        return {}
    path = Path(row.path)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def load_auth_signals(
    session: Session,
    *,
    app_id: uuid.UUID,
    pipeline_run_id: uuid.UUID | None = None,
) -> dict:
    direct = None
    if pipeline_run_id is not None:
        direct = artifact_storage_root() / "auth_signals" / str(app_id) / f"{pipeline_run_id}.json"
    return _load_latest_artifact_json(
        session,
        app_id=app_id,
        pipeline_run_id=pipeline_run_id,
        path_fragment="auth_signals",
        direct_path=direct,
    )


def load_persona_visibility(
    session: Session,
    *,
    app_id: uuid.UUID,
    pipeline_run_id: uuid.UUID | None = None,
) -> dict:
    direct = None
    if pipeline_run_id is not None:
        direct = artifact_storage_root() / "persona_visibility" / str(app_id) / f"{pipeline_run_id}.json"
    return _load_latest_artifact_json(
        session,
        app_id=app_id,
        pipeline_run_id=pipeline_run_id,
        path_fragment="persona_visibility",
        direct_path=direct,
    )


def load_spa_route_events(
    session: Session,
    *,
    app_id: uuid.UUID,
    pipeline_run_id: uuid.UUID | None = None,
) -> list[dict]:
    direct = None
    if pipeline_run_id is not None:
        direct = artifact_storage_root() / "spa_routes" / str(app_id) / f"{pipeline_run_id}.json"
    payload = _load_latest_artifact_json(
        session,
        app_id=app_id,
        pipeline_run_id=pipeline_run_id,
        path_fragment="spa_routes",
        direct_path=direct,
    )
    events = payload.get("events") or []
    return events if isinstance(events, list) else []


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


def _load_appmap_records(
    session: Session, app_id: uuid.UUID
) -> tuple[
    list[Page],
    list[Element],
    list[PageState],
    list[StateTransitionRow],
    list[PageDiscovery],
    list[Form],
    list[ApiEndpoint],
    list[ApiUiMapping],
]:
    pages = list(session.scalars(select(Page).where(Page.app_id == app_id).order_by(Page.url)).all())
    elements = list(
        session.scalars(
            select(Element).join(Page).where(Page.app_id == app_id).order_by(Element.page_id)
        ).all()
    )
    states = list(
        session.scalars(
            select(PageState).join(Page).where(Page.app_id == app_id).order_by(PageState.page_id)
        ).all()
    )
    transitions = list(
        session.scalars(select(StateTransitionRow).where(StateTransitionRow.app_id == app_id)).all()
    )
    discoveries = list(
        session.scalars(select(PageDiscovery).where(PageDiscovery.app_id == app_id).order_by(PageDiscovery.url)).all()
    )
    forms = list(session.scalars(select(Form).where(Form.app_id == app_id).order_by(Form.page_id)).all())
    api_endpoints = list(
        session.scalars(select(ApiEndpoint).where(ApiEndpoint.app_id == app_id).order_by(ApiEndpoint.path_pattern)).all()
    )
    api_ui_mappings = list(
        session.scalars(select(ApiUiMapping).where(ApiUiMapping.app_id == app_id)).all()
    )
    return pages, elements, states, transitions, discoveries, forms, api_endpoints, api_ui_mappings


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
            "state_id": str(element.state_id) if element.state_id else None,
            "tag_name": element.tag_name,
            "role": element.role,
            "semantic_selector": element.semantic_selector,
            "xpath_fallback": element.xpath_fallback,
            "text_content": element.text_content,
            "attributes": dict(element.attributes or {}),
        }
        for element in elements
    ]


def _serialize_states(states: list[PageState]) -> list[dict]:
    return [
        {
            "state_id": str(state.state_id),
            "page_id": str(state.page_id),
            "state_key": state.state_key,
            "fingerprint": state.fingerprint,
            "title": state.title,
            "screenshot_path": state.screenshot_path,
            "interaction_depth": state.interaction_depth,
            "parent_state_key": state.parent_state_key,
            "trigger_action": dict(state.trigger_action or {}),
        }
        for state in states
    ]


def _serialize_discoveries(discoveries: list[PageDiscovery]) -> list[dict]:
    return [
        {
            "discovery_id": str(row.discovery_id),
            "url": row.url,
            "discovered_via": row.discovered_via,
            "source_page_id": str(row.source_page_id) if row.source_page_id else None,
            "source_state_key": row.source_state_key,
            "trigger_action": dict(row.trigger_action or {}),
        }
        for row in discoveries
    ]


def _serialize_api_endpoints(endpoints: list[ApiEndpoint]) -> list[dict]:
    output: list[dict] = []
    for endpoint in endpoints:
        method = str(endpoint.method or "GET").upper()
        risk = 30
        if method not in {"GET", "HEAD", "OPTIONS"}:
            risk += 35
        if any(kw in str(endpoint.path_pattern or "").lower() for kw in ("user", "auth", "payment", "admin")):
            risk += 20
        output.append(
            {
                "endpoint_id": str(endpoint.endpoint_id),
                "method": method,
                "path": endpoint.path,
                "path_pattern": endpoint.path_pattern,
                "source": endpoint.source,
                "request_schema": dict(endpoint.request_schema or {}),
                "response_schema": dict(endpoint.response_schema or {}),
                "seen_on_page_ids": [str(page_id) for page_id in (endpoint.seen_page_ids or [])],
                "first_seen_page_id": str(endpoint.first_seen_page_id) if endpoint.first_seen_page_id else None,
                "seen_count": int(endpoint.seen_count or 1),
                "risk_score": max(0, min(100, risk)),
            }
        )
    return output


def _serialize_forms(forms: list[Form]) -> list[dict]:
    output: list[dict] = []
    for form in forms:
        field_ids = [str(item) for item in (form.field_element_ids or [])]
        method = str(form.method or "get").lower()
        attrs = dict(form.attributes or {})
        risk = 20
        if method not in {"", "get"}:
            risk += 25
        risk += min(20, len(field_ids) * 2)
        name_blob = f"{attrs.get('name', '')} {form.action or ''}".lower()
        if any(kw in name_blob for kw in ("login", "register", "payment", "checkout", "password")):
            risk += 20
        output.append(
            {
                "form_id": str(form.form_id),
                "page_id": str(form.page_id),
                "state_id": str(form.state_id) if form.state_id else None,
                "name": str(attrs.get("name") or attrs.get("form_key") or "Form"),
                "action": form.action,
                "method": method,
                "attributes": attrs,
                "field_element_ids": field_ids,
                "risk_score": max(0, min(100, risk)),
            }
        )
    return output


def _serialize_api_ui_mappings(mappings: list[ApiUiMapping]) -> list[dict]:
    return [
        {
            "mapping_id": str(row.mapping_id),
            "api_endpoint_id": str(row.api_endpoint_id),
            "page_id": str(row.page_id),
            "form_id": str(row.form_id) if row.form_id else None,
            "element_id": str(row.element_id) if row.element_id else None,
            "flow_id": str(row.flow_id) if row.flow_id else None,
            "trigger_action": dict(row.trigger_action or {}),
            "confidence": float(row.confidence or 0),
            "correlation_method": row.correlation_method,
            "review_required": bool(row.review_required),
        }
        for row in mappings
    ]


def _api_ui_mapping_dicts(
    *,
    mappings_orm: list[ApiUiMapping],
    page_dicts: list[dict],
    form_dicts: list[dict],
    element_dicts: list[dict],
    api_endpoint_dicts: list[dict],
) -> list[dict]:
    if mappings_orm:
        return _serialize_api_ui_mappings(mappings_orm)
    from aqa_shared.discovery.api_ui_mapper import build_api_ui_mappings

    return build_api_ui_mappings(
        pages=page_dicts,
        forms=form_dicts,
        elements=element_dicts,
        api_endpoints=api_endpoint_dicts,
    )


def _serialize_transitions(transitions: list[StateTransitionRow]) -> list[dict]:
    return [
        {
            "transition_id": str(row.transition_id),
            "from_state_id": str(row.from_state_id),
            "to_state_id": str(row.to_state_id),
            "action": dict(row.action or {}),
        }
        for row in transitions
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


def _flow_output_dict(flow: Flow, source_def: dict | None = None) -> dict:
    item = source_def or {}
    output = {
        "flow_id": str(flow.flow_id),
        "name": flow.name,
        "description": flow.description,
        "source": flow.source.value,
        "steps": list(flow.sequence or []),
    }
    for key in ("confidence", "confidence_factors", "review_required", "module", "module_id"):
        if key in item:
            output[key] = item[key]
    return output


def _flow_output_from_defs(persisted_flows: list[Flow], flow_defs: list[dict]) -> list[dict]:
    if len(persisted_flows) == len(flow_defs):
        return [_flow_output_dict(flow, item) for flow, item in zip(persisted_flows, flow_defs)]
    return [_flow_output_dict(flow) for flow in persisted_flows]


def build_appmap_document(
    *,
    application_id: uuid.UUID,
    last_crawl_at: datetime | None,
    pages: list[dict],
    elements: list[dict],
    flows: list[dict],
    states: list[dict] | None = None,
    transitions: list[dict] | None = None,
    modules: list[dict] | None = None,
    navigation_graph: list[dict] | None = None,
    forms: list[dict] | None = None,
    api_endpoints: list[dict] | None = None,
    api_ui_mappings: list[dict] | None = None,
    data_entities: list[dict] | None = None,
    api_dependency_graph: dict | None = None,
    auth_intelligence: dict | None = None,
    test_data_catalog: list[dict] | None = None,
    spa_routes: list[dict] | None = None,
    scoring_summary: dict | None = None,
    discovery_completeness_score: int | None = None,
    recommendations: list[str] | None = None,
) -> dict:
    state_list = states or []
    transition_list = transitions or []
    module_list = modules or []
    nav_list = navigation_graph or []

    if module_list:
        schema_version = 3
    elif state_list:
        schema_version = 2
    else:
        schema_version = 1

    flow_docs = []
    for flow in flows:
        doc = {
            "flow_id": flow.get("flow_id"),
            "name": flow.get("name"),
            "description": flow.get("description"),
            "source": flow.get("source"),
            "steps": flow.get("steps") or flow.get("sequence") or [],
        }
        for key in (
            "confidence",
            "confidence_factors",
            "review_required",
            "module",
            "module_id",
            "risk_score",
            "risk_factors",
            "testability_score",
            "automation_complexity_score",
            "complexity_factors",
        ):
            if key in flow:
                doc[key] = flow[key]
        flow_docs.append(doc)

    doc = {
        "schema_version": schema_version,
        "application_id": str(application_id),
        "last_crawl_at": last_crawl_at.isoformat() if last_crawl_at else None,
        "pages": pages,
        "elements": elements,
        "flows": flow_docs,
        "stats": {
            "page_count": len(pages),
            "element_count": len(elements),
            "flow_count": len(flows),
            "state_count": len(state_list),
            "interaction_count": len(transition_list),
            "module_count": len(module_list),
        },
    }
    if state_list:
        doc["states"] = state_list
    if transition_list:
        doc["transitions"] = transition_list
    if module_list:
        doc["modules"] = module_list
        doc["mvp"] = True
    if nav_list:
        doc["navigation_graph"] = nav_list
    api_list = api_endpoints or []
    if api_list:
        doc["api_endpoints"] = api_list
        doc["stats"]["api_endpoint_count"] = len(api_list)
    form_list = forms or []
    if form_list:
        doc["forms"] = form_list
        doc["stats"]["form_count"] = len(form_list)
    mapping_list = api_ui_mappings or []
    if mapping_list:
        doc["api_ui_mappings"] = mapping_list
        doc["stats"]["api_ui_mapping_count"] = len(mapping_list)
    entity_list = data_entities or []
    if entity_list:
        doc["data_entities"] = entity_list
        doc["stats"]["entity_count"] = len(entity_list)
        doc.setdefault("inventory", {})
        doc["inventory"]["entities"] = len(entity_list)
    if api_dependency_graph and (api_dependency_graph.get("nodes") or api_dependency_graph.get("edges")):
        doc["api_dependency_graph"] = api_dependency_graph
        doc["stats"]["api_dependency_edge_count"] = len(api_dependency_graph.get("edges") or [])
        doc.setdefault("inventory", {})
        doc["inventory"]["api_dependency_edges"] = len(api_dependency_graph.get("edges") or [])
    catalog_list = test_data_catalog or []
    if catalog_list:
        doc["test_data_catalog"] = catalog_list
        doc["stats"]["test_data_catalog_count"] = len(catalog_list)
    if auth_intelligence:
        doc["auth_intelligence"] = auth_intelligence
    spa_route_list = spa_routes or []
    if spa_route_list:
        doc["spa_routes"] = spa_route_list
        doc["stats"]["spa_route_count"] = len(spa_route_list)
        doc.setdefault("inventory", {})
        doc["inventory"]["spa_routes"] = len(spa_route_list)
    if scoring_summary:
        doc["scoring_summary"] = scoring_summary
    if discovery_completeness_score is not None:
        doc["discovery_completeness_score"] = discovery_completeness_score
    if recommendations:
        doc["recommendations"] = recommendations
    return doc


def build_and_persist_appmap(
    *,
    application_id: uuid.UUID,
    pipeline_run_id: uuid.UUID,
    db: Session | None = None,
    use_llm: bool = True,
    token_budget_remaining: int = 8000,
) -> AppMapBuildResult:
    """Load crawl results, build flows, write AppMap JSON artifact, persist flows."""
    from aqa_agents.discovery.flow_structure import structure_flows_with_llm
    from aqa_agents.discovery.module_tree import build_modules_rule_pass, structure_modules_with_llm
    from aqa_shared.discovery.approval import mark_appmap_pending
    from aqa_shared.llm.budget import LlmBudgetTracker

    owns_session = db is None
    session = db or get_session_factory()()
    try:
        app = session.get(Application, application_id)
        if app is None:
            raise ValueError(f"Application not found: {application_id}")

        run = session.get(PipelineRun, pipeline_run_id)
        discover_config: dict = {}
        if run is not None and run.config:
            discover_config = dict(run.config)
            use_llm = bool(discover_config.get("use_llm", use_llm))

        budget_tracker = LlmBudgetTracker.from_discover_config(discover_config)
        flow_budget = budget_tracker.remaining_for_stage("flow_structure")
        module_budget = budget_tracker.remaining_for_stage("module_structure")
        if token_budget_remaining > 0:
            flow_budget = min(flow_budget, token_budget_remaining)

        pages_orm, elements_orm, states_orm, transitions_orm, discoveries_orm, forms_orm, api_endpoints_orm, mappings_orm = _load_appmap_records(
            session, application_id
        )
        page_dicts = _serialize_pages(pages_orm)
        element_dicts = _serialize_elements(elements_orm)
        state_dicts = _serialize_states(states_orm)
        transition_dicts = _serialize_transitions(transitions_orm)
        discovery_dicts = _serialize_discoveries(discoveries_orm)
        form_dicts = _serialize_forms(forms_orm)
        api_endpoint_dicts = _serialize_api_endpoints(api_endpoints_orm)
        api_ui_mapping_dicts = _api_ui_mapping_dicts(
            mappings_orm=mappings_orm,
            page_dicts=page_dicts,
            form_dicts=form_dicts,
            element_dicts=element_dicts,
            api_endpoint_dicts=api_endpoint_dicts,
        )
        if state_dicts or discovery_dicts:
            rule_flow_defs = build_flows_from_states(
                page_dicts,
                state_dicts,
                transition_dicts,
                discoveries=discovery_dicts,
                max_graph_paths_per_page=5,
            )
        else:
            rule_flow_defs = build_flows_from_pages(page_dicts)

        flow_defs, tokens_used, cost_estimate, llm_skip_reason = structure_flows_with_llm(
            pages=page_dicts,
            elements=element_dicts,
            rule_flows=rule_flow_defs,
            use_llm=use_llm,
            token_budget_remaining=flow_budget,
            llm_stage="flow_structure",
        )
        budget_tracker.record_usage("flow_structure", tokens_used)

        persisted_flows = _replace_crawler_flows(session, application_id, flow_defs)
        flow_output = _flow_output_from_defs(persisted_flows, flow_defs)

        rule_modules, navigation_graph = build_modules_rule_pass(
            pages=page_dicts,
            flows=flow_output,
            elements=element_dicts,
            discoveries=discovery_dicts,
        )
        modules, module_tokens, module_cost, module_skip = structure_modules_with_llm(
            pages=page_dicts,
            flows=flow_output,
            rule_modules=rule_modules,
            navigation_graph=navigation_graph,
            use_llm=use_llm,
            token_budget_remaining=module_budget,
            llm_stage="module_structure",
        )
        budget_tracker.record_usage("module_structure", module_tokens)
        tokens_used += module_tokens
        cost_estimate += module_cost

        from aqa_agents.discovery.entities import (
            build_entities_rule_pass,
            link_flows_to_modules,
            structure_entities_with_llm,
        )
        from aqa_agents.discovery.scoring import apply_scoring

        flow_output = link_flows_to_modules(flow_output, page_dicts, modules)
        entity_budget = budget_tracker.remaining_for_stage("entities")
        rule_entities = build_entities_rule_pass(
            pages=page_dicts,
            elements=element_dicts,
            forms=form_dicts,
            api_endpoints=api_endpoint_dicts,
            modules=modules,
            api_ui_mappings=api_ui_mapping_dicts,
        )
        data_entities, entity_tokens, entity_cost, entity_skip = structure_entities_with_llm(
            rule_entities=rule_entities,
            use_llm=use_llm,
            token_budget_remaining=entity_budget,
            llm_stage="entities",
        )
        budget_tracker.record_usage("entities", entity_tokens)
        tokens_used += entity_tokens
        cost_estimate += entity_cost

        from aqa_agents.discovery.api_dependency_graph import build_api_dependency_graph

        network_events_by_page = load_network_timeline(
            session, app_id=application_id, pipeline_run_id=pipeline_run_id
        )
        api_dependency_graph = build_api_dependency_graph(
            api_endpoints=api_endpoint_dicts,
            api_ui_mappings=api_ui_mapping_dicts,
            network_events_by_page=network_events_by_page,
        )

        from aqa_shared.discovery.auth_intelligence import build_auth_intelligence
        from aqa_shared.discovery.test_data_discovery import build_test_data_catalog

        auth_signals = load_auth_signals(
            session, app_id=application_id, pipeline_run_id=pipeline_run_id
        )
        persona_visibility = load_persona_visibility(
            session, app_id=application_id, pipeline_run_id=pipeline_run_id
        )
        test_data_catalog = build_test_data_catalog(
            forms=form_dicts,
            elements=element_dicts,
            api_endpoints=api_endpoint_dicts,
            data_entities=data_entities,
            run_id=str(pipeline_run_id),
        )
        auth_intelligence = build_auth_intelligence(
            pages=page_dicts,
            forms=form_dicts,
            flows=flow_output,
            elements=element_dicts,
            api_endpoints=api_endpoint_dicts,
            modules=modules,
            persona_visibility=persona_visibility,
            auth_signals=auth_signals,
            crawl_authenticated=bool(auth_signals.get("authenticated")),
        )

        from aqa_shared.discovery.spa_routes import build_spa_routes

        spa_route_events = load_spa_route_events(
            session, app_id=application_id, pipeline_run_id=pipeline_run_id
        )
        spa_routes = build_spa_routes(
            pages=page_dicts,
            modules=modules,
            discoveries=discovery_dicts,
            transitions=transition_dicts,
            crawl_events=spa_route_events,
        )

        crawl_config = dict(app.crawl_config or {})
        crawl_config.update(discover_config.get("crawlConfigOverrides") or {})
        scored = apply_scoring(
            pages=page_dicts,
            elements=element_dicts,
            flows=flow_output,
            modules=modules,
            states=state_dicts,
            navigation_graph=navigation_graph,
            crawl_config=crawl_config,
            forms=form_dicts,
            api_endpoints=api_endpoint_dicts,
            api_ui_mappings=api_ui_mapping_dicts,
            data_entities=data_entities,
            spa_routes=spa_routes,
        )
        modules = scored["modules"]
        flow_output = scored["flows"]

        appmap_doc = build_appmap_document(
            application_id=application_id,
            last_crawl_at=app.last_crawl_at,
            pages=page_dicts,
            elements=element_dicts,
            flows=flow_output,
            states=state_dicts,
            transitions=transition_dicts,
            modules=modules,
            navigation_graph=navigation_graph,
            forms=form_dicts,
            api_endpoints=api_endpoint_dicts,
            api_ui_mappings=api_ui_mapping_dicts,
            data_entities=data_entities,
            api_dependency_graph=api_dependency_graph,
            auth_intelligence=auth_intelligence,
            test_data_catalog=test_data_catalog,
            spa_routes=spa_routes,
            scoring_summary=scored["scoring_summary"],
            discovery_completeness_score=scored["discovery_completeness_score"],
            recommendations=scored["recommendations"],
        )
        appmap_hash = _compute_appmap_hash(page_dicts, flow_output, len(element_dicts))

        dest = appmap_artifact_path(pipeline_run_id)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(appmap_doc, indent=2), encoding="utf-8")
        _register_appmap_artifact(session, pipeline_run_id=pipeline_run_id, path=dest)

        run = session.get(PipelineRun, pipeline_run_id)
        if run is not None:
            config = mark_appmap_pending(dict(run.config or {}))
            config["appmap_hash"] = appmap_hash
            config["appmap_path"] = str(dest)
            config["discovery_stats"] = {
                "page_count": len(page_dicts),
                "element_count": len(element_dicts),
                "flow_count": len(flow_output),
                "state_count": len(state_dicts),
                "module_count": len(modules),
                "entity_count": len(data_entities),
                "api_dependency_edge_count": len(api_dependency_graph.get("edges") or []),
            }
            if module_skip:
                config["module_llm_skip_reason"] = module_skip
            config["llm_budget_usage"] = budget_tracker.usage_snapshot()
            if tokens_used:
                config["discovery_llm_tokens_used"] = tokens_used
                config["discovery_llm_cost_estimate"] = cost_estimate
            if llm_skip_reason:
                config["discovery_llm_skip_reason"] = llm_skip_reason
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
            tokens_used=tokens_used,
            cost_estimate=cost_estimate,
            llm_skip_reason=llm_skip_reason,
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
    from aqa_agents.discovery.entities import build_entities_rule_pass, link_flows_to_modules
    from aqa_agents.discovery.module_tree import build_modules_rule_pass
    from aqa_agents.discovery.scoring import apply_scoring

    app = session.get(Application, app_id)
    if app is None:
        return None

    pages_orm, elements_orm, states_orm, transitions_orm, discoveries_orm, forms_orm, api_endpoints_orm, mappings_orm = _load_appmap_records(
        session, app_id
    )
    flows_orm = list(
        session.scalars(select(Flow).where(Flow.app_id == app_id).order_by(Flow.name)).all()
    )
    page_dicts = _serialize_pages(pages_orm)
    element_dicts = _serialize_elements(elements_orm)
    state_dicts = _serialize_states(states_orm)
    transition_dicts = _serialize_transitions(transitions_orm)
    discovery_dicts = _serialize_discoveries(discoveries_orm)
    form_dicts = _serialize_forms(forms_orm)
    api_endpoint_dicts = _serialize_api_endpoints(api_endpoints_orm)
    api_ui_mapping_dicts = _api_ui_mapping_dicts(
        mappings_orm=mappings_orm,
        page_dicts=page_dicts,
        form_dicts=form_dicts,
        element_dicts=element_dicts,
        api_endpoint_dicts=api_endpoint_dicts,
    )
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
    modules, navigation_graph = build_modules_rule_pass(
        pages=page_dicts,
        flows=flow_output,
        elements=element_dicts,
        discoveries=discovery_dicts,
    )
    flow_output = link_flows_to_modules(flow_output, page_dicts, modules)
    data_entities = build_entities_rule_pass(
        pages=page_dicts,
        elements=element_dicts,
        forms=form_dicts,
        api_endpoints=api_endpoint_dicts,
        modules=modules,
        api_ui_mappings=api_ui_mapping_dicts,
    )
    from aqa_agents.discovery.api_dependency_graph import build_api_dependency_graph

    network_events_by_page = load_network_timeline(session, app_id=app_id)
    api_dependency_graph = build_api_dependency_graph(
        api_endpoints=api_endpoint_dicts,
        api_ui_mappings=api_ui_mapping_dicts,
        network_events_by_page=network_events_by_page,
    )
    from aqa_shared.discovery.auth_intelligence import build_auth_intelligence
    from aqa_shared.discovery.test_data_discovery import build_test_data_catalog

    auth_signals = load_auth_signals(session, app_id=app_id)
    persona_visibility = load_persona_visibility(session, app_id=app_id)
    test_data_catalog = build_test_data_catalog(
        forms=form_dicts,
        elements=element_dicts,
        api_endpoints=api_endpoint_dicts,
        data_entities=data_entities,
    )
    auth_intelligence = build_auth_intelligence(
        pages=page_dicts,
        forms=form_dicts,
        flows=flow_output,
        elements=element_dicts,
        api_endpoints=api_endpoint_dicts,
        modules=modules,
        persona_visibility=persona_visibility,
        auth_signals=auth_signals,
        crawl_authenticated=bool(auth_signals.get("authenticated")),
    )
    from aqa_shared.discovery.spa_routes import build_spa_routes

    spa_route_events = load_spa_route_events(session, app_id=app_id)
    spa_routes = build_spa_routes(
        pages=page_dicts,
        modules=modules,
        discoveries=discovery_dicts,
        transitions=transition_dicts,
        crawl_events=spa_route_events,
    )
    scored = apply_scoring(
        pages=page_dicts,
        elements=element_dicts,
        flows=flow_output,
        modules=modules,
        states=state_dicts,
        navigation_graph=navigation_graph,
        crawl_config=dict(app.crawl_config or {}),
        forms=form_dicts,
        api_endpoints=api_endpoint_dicts,
        api_ui_mappings=api_ui_mapping_dicts,
        data_entities=data_entities,
        spa_routes=spa_routes,
    )
    document = build_appmap_document(
        application_id=app_id,
        last_crawl_at=app.last_crawl_at,
        pages=page_dicts,
        elements=element_dicts,
        flows=scored["flows"],
        states=state_dicts,
        transitions=transition_dicts,
        modules=scored["modules"],
        navigation_graph=navigation_graph,
        forms=form_dicts,
        api_endpoints=api_endpoint_dicts,
        api_ui_mappings=api_ui_mapping_dicts,
        data_entities=data_entities,
        api_dependency_graph=api_dependency_graph,
        auth_intelligence=auth_intelligence,
        test_data_catalog=test_data_catalog,
        spa_routes=spa_routes,
        scoring_summary=scored["scoring_summary"],
        discovery_completeness_score=scored["discovery_completeness_score"],
        recommendations=scored["recommendations"],
    )
    document["discoveries"] = discovery_dicts
    return document
