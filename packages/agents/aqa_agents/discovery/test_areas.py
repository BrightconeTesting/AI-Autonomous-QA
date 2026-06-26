"""Recommended test areas for AppMap v3 (DISCOVERY-AGENT-VISION-SPEC §9.6)."""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any

from aqa_agents.discovery.scoring import DESTRUCTIVE_KEYWORDS, compute_priority_index
from aqa_shared.discovery.confidence import REVIEW_THRESHOLD, attach_confidence
from aqa_shared.discovery.test_data_discovery import canonicalize_forms
from aqa_shared.llm.settings import estimate_cost_usd, llm_available, openai_api_key, openai_model

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "test-areas.v1.txt"

AREA_TYPES = (
    "form_validation",
    "destructive_control",
    "api_contract",
    "entity_coverage_gap",
    "auth_flow",
)


def _priority_label(priority_index: int) -> str:
    if priority_index >= 75:
        return "critical"
    if priority_index >= 60:
        return "high"
    if priority_index >= 40:
        return "medium"
    return "low"


def _endpoint_mapped(endpoint_id: str, api_ui_mappings: list[dict[str, Any]]) -> bool:
    return any(
        str(mapping.get("api_endpoint_id") or "") == endpoint_id
        and float(mapping.get("confidence") or 0) >= 0.7
        for mapping in api_ui_mappings
    )


def _form_mapped(form_id: str, api_ui_mappings: list[dict[str, Any]]) -> bool:
    return any(
        str(mapping.get("form_id") or "") == form_id
        and float(mapping.get("confidence") or 0) >= 0.7
        for mapping in api_ui_mappings
    )


def _module_for_page(page_id: str, modules: list[dict[str, Any]]) -> str | None:
    for module in modules:
        if page_id in [str(item) for item in (module.get("pages") or [])]:
            return str(module.get("module_id") or "") or None
    return None


def _flow_ids_for_module(module_id: str | None, flows: list[dict[str, Any]]) -> set[str]:
    if not module_id:
        return set()
    return {
        str(flow.get("flow_id") or "")
        for flow in flows
        if str(flow.get("module_id") or "") == module_id and flow.get("flow_id")
    }


def build_test_areas_rule_pass(
    *,
    pages: list[dict[str, Any]],
    elements: list[dict[str, Any]],
    forms: list[dict[str, Any]],
    api_endpoints: list[dict[str, Any]],
    api_ui_mappings: list[dict[str, Any]] | None,
    data_entities: list[dict[str, Any]] | None,
    flows: list[dict[str, Any]],
    modules: list[dict[str, Any]],
    auth_intelligence: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Rule-generated recommended test areas (always runs)."""
    api_ui_mappings = list(api_ui_mappings or [])
    data_entities = list(data_entities or [])
    auth_intelligence = auth_intelligence or {}
    areas: list[dict[str, Any]] = []
    seen_signals: set[tuple[str, ...]] = set()

    def _add(area: dict[str, Any]) -> None:
        signals = tuple(sorted(str(item) for item in (area.get("signals") or [])))
        if signals in seen_signals:
            return
        seen_signals.add(signals)
        priority_index = int(area.get("priority_index") or compute_priority_index(
            risk_score=int(area.get("risk_score") or 0),
            business_criticality=str(area.get("business_criticality") or "medium"),
            testability_score=int(area.get("testability_score") or 50),
            automation_complexity_score=int(area.get("automation_complexity_score") or 30),
        ))
        confidence = float(area.get("confidence") or 0.85)
        payload = attach_confidence(
            {
                **area,
                "area_id": str(area.get("area_id") or uuid.uuid4()),
                "priority_index": priority_index,
                "priority": area.get("priority") or _priority_label(priority_index),
            },
            confidence=confidence,
            factors=list(area.get("confidence_factors") or ["rule:deterministic"]),
        )
        areas.append(payload)

    pages_by_id = {str(page.get("page_id") or ""): page for page in pages if page.get("page_id")}

    canonical_forms = canonicalize_forms(forms, elements=elements)

    for form in canonical_forms:
        form_id = str(form.get("form_id") or "")
        page_id = str(form.get("page_id") or "")
        method = str(form.get("method") or "get").lower()
        if not form_id:
            continue
        module_id = _module_for_page(page_id, modules)
        form_name = str(form.get("name") or form.get("attributes", {}).get("name") or "form")
        risk = int(form.get("risk_score") or 20)
        testability = int(form.get("testability_score") or 50)
        mapped = _form_mapped(form_id, api_ui_mappings)
        signals = [f"form:{form_id}"]
        if method not in {"", "get"}:
            area_type = "form_validation"
            rationale = f"Validate {form_name} ({method.upper()}) field rules and submission behavior"
            if not mapped:
                rationale += "; no high-confidence API mapping yet"
                signals.append("gap:unmapped_form_api")
            confidence = 0.9 if mapped else 0.8
        else:
            area_type = "form_validation"
            rationale = f"Exercise read-only or GET form {form_name} for field visibility and defaults"
            confidence = 0.75
        _add(
            {
                "area": f"{form_name} validation",
                "area_type": area_type,
                "module_id": module_id,
                "page_id": page_id,
                "form_id": form_id,
                "risk_score": risk,
                "testability_score": testability,
                "automation_complexity_score": 25 if mapped else 35,
                "business_criticality": next(
                    (str(module.get("business_criticality") or "medium") for module in modules if str(module.get("module_id")) == module_id),
                    "medium",
                ),
                "rationale": rationale,
                "signals": signals,
                "confidence": confidence,
                "confidence_factors": ["rule:form_surface", "grounded:form_id"],
            }
        )

    elements_by_page: dict[str, list[dict[str, Any]]] = {}
    for element in elements:
        page_id = str(element.get("page_id") or "")
        elements_by_page.setdefault(page_id, []).append(element)

    for page_id, page_elements in elements_by_page.items():
        page = pages_by_id.get(page_id) or {}
        module_id = _module_for_page(page_id, modules)
        for element in page_elements:
            text = str(element.get("text_content") or "").lower()
            if not any(kw in text for kw in DESTRUCTIVE_KEYWORDS):
                continue
            element_id = str(element.get("element_id") or "")
            if not element_id:
                continue
            label = (element.get("text_content") or "destructive control").strip()[:60]
            _add(
                {
                    "area": f"Destructive control — {label}",
                    "area_type": "destructive_control",
                    "module_id": module_id,
                    "page_id": page_id,
                    "element_id": element_id,
                    "risk_score": 70,
                    "testability_score": int(element.get("testability_score") or 50),
                    "automation_complexity_score": 40,
                    "business_criticality": "high",
                    "rationale": f"Negative/destructive path for \"{label}\" on {page.get('title') or page.get('url') or 'page'}",
                    "signals": [f"element:{element_id}", "destructive:ui"],
                    "confidence": 0.75,
                    "confidence_factors": ["rule:destructive_control", "grounded:element_id"],
                }
            )

    for endpoint in api_endpoints:
        endpoint_id = str(endpoint.get("endpoint_id") or "")
        method = str(endpoint.get("method") or "GET").upper()
        if not endpoint_id or method in {"GET", "HEAD", "OPTIONS"}:
            continue
        if _endpoint_mapped(endpoint_id, api_ui_mappings):
            continue
        path = str(endpoint.get("path_pattern") or endpoint.get("path") or "")
        page_ids = [str(item) for item in (endpoint.get("seen_on_page_ids") or [])]
        module_id = _module_for_page(page_ids[0], modules) if page_ids else None
        _add(
            {
                "area": f"API contract — {method} {path}",
                "area_type": "api_contract",
                "module_id": module_id,
                "api_endpoint_id": endpoint_id,
                "risk_score": int(endpoint.get("risk_score") or 45),
                "testability_score": 60,
                "automation_complexity_score": int(endpoint.get("automation_complexity_score") or 35),
                "business_criticality": "medium",
                "rationale": f"Mutating API {method} {path} lacks UI mapping — verify contract and error handling",
                "signals": [f"api:{method}:{path}", f"endpoint:{endpoint_id}", "gap:unmapped_api"],
                "confidence": 0.85,
                "confidence_factors": ["rule:mutating_api", "grounded:endpoint_id"],
            }
        )

    for entity in data_entities:
        entity_id = str(entity.get("entity_id") or "")
        module_id = str(entity.get("module_id") or "") or None
        module_flow_ids = _flow_ids_for_module(module_id, flows)
        crud = entity.get("crud_surfaces") or {}
        has_surface = any(
            isinstance(surface, dict)
            and (surface.get("api_endpoint_ids") or surface.get("form_ids") or surface.get("page_ids"))
            for surface in crud.values()
        )
        if not has_surface:
            continue
        if module_flow_ids:
            continue
        _add(
            {
                "area": f"Entity coverage — {entity.get('name') or entity_id}",
                "area_type": "entity_coverage_gap",
                "module_id": module_id,
                "entity_id": entity_id,
                "risk_score": int(entity.get("risk_score") or 35),
                "testability_score": int(entity.get("testability_score") or 55),
                "automation_complexity_score": int(entity.get("automation_complexity_score") or 30),
                "business_criticality": str(entity.get("business_criticality") or "medium"),
                "rationale": f"CRUD surfaces exist for {entity.get('name') or entity_id} but no grounded flow covers the journey",
                "signals": [f"entity:{entity_id}", "gap:missing_flow"],
                "confidence": 0.7,
                "confidence_factors": ["rule:entity_crud", "grounded:entity_id"],
            }
        )

    if auth_intelligence.get("login_flow_id") or auth_intelligence.get("login_api_endpoint_id"):
        login_flow = str(auth_intelligence.get("login_flow_id") or "")
        login_api = str(auth_intelligence.get("login_api_endpoint_id") or "")
        signals = []
        if login_flow:
            signals.append(f"flow:{login_flow}")
        if login_api:
            signals.append(f"endpoint:{login_api}")
        _add(
            {
                "area": "Authentication and session",
                "area_type": "auth_flow",
                "module_id": None,
                "risk_score": 75,
                "testability_score": 50,
                "automation_complexity_score": 45,
                "business_criticality": "critical",
                "rationale": "Login/session behavior detected — verify auth success, failure, and protected routes",
                "signals": signals or ["auth:detected"],
                "confidence": 0.8,
                "confidence_factors": ["rule:auth_intelligence", "grounded:auth_signals"],
            }
        )

    areas.sort(key=lambda item: float(item.get("priority_index") or 0), reverse=True)
    return areas


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM response did not contain a JSON object")
    return json.loads(cleaned[start : end + 1])


def _merge_llm_test_areas(
    rule_areas: list[dict[str, Any]],
    llm_areas: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id = {str(area.get("area_id") or ""): dict(area) for area in rule_areas if area.get("area_id")}
    for item in llm_areas:
        area_id = str(item.get("area_id") or "")
        if area_id not in by_id:
            continue
        merged = by_id[area_id]
        if item.get("area"):
            merged["area"] = str(item["area"])[:255]
        if item.get("rationale"):
            merged["rationale"] = str(item["rationale"])[:512]
        input_signals = set(str(signal) for signal in (merged.get("signals") or []))
        llm_signals = [str(signal) for signal in (item.get("signals") or []) if str(signal) in input_signals]
        if llm_signals:
            merged["signals"] = llm_signals
        merged["confidence_factors"] = sorted(
            set(merged.get("confidence_factors") or []) | {"llm:rationale_only"}
        )
        cap = float(merged.get("confidence") or 0.85)
        merged["confidence"] = round(min(cap, 0.95), 3)
        merged["review_required"] = merged["confidence"] < REVIEW_THRESHOLD
    return sorted(by_id.values(), key=lambda item: float(item.get("priority_index") or 0), reverse=True)


def structure_test_areas_with_llm(
    *,
    rule_areas: list[dict[str, Any]],
    modules: list[dict[str, Any]],
    use_llm: bool,
    token_budget_remaining: int,
    max_areas: int = 12,
    llm_stage: str = "test_areas",
) -> tuple[list[dict[str, Any]], int, float, str | None]:
    """Return (areas, tokens_used, cost_estimate, skip_reason)."""
    if not rule_areas:
        return [], 0, 0.0, "no rule test areas"
    if not use_llm:
        return rule_areas, 0, 0.0, "use_llm=false"
    if not llm_available(use_llm=True):
        return rule_areas, 0, 0.0, "OPENAI_API_KEY unset"
    if token_budget_remaining <= 0:
        return rule_areas, 0, 0.0, f"{llm_stage} budget exhausted"

    top_areas = rule_areas[:max_areas]
    top_modules = sorted(modules, key=lambda item: float(item.get("priority_index") or 0), reverse=True)[:8]
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    prompt = (
        template.replace("{{max_areas}}", str(max_areas))
        .replace("{{test_areas_json}}", json.dumps(top_areas, separators=(",", ":"))[:12000])
        .replace(
            "{{modules_json}}",
            json.dumps(
                [
                    {
                        "module_id": module.get("module_id"),
                        "name": module.get("name"),
                        "priority_index": module.get("priority_index"),
                        "business_criticality": module.get("business_criticality"),
                    }
                    for module in top_modules
                ],
                separators=(",", ":"),
            ),
        )
    )

    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai package not installed; skipping test area LLM pass")
        return rule_areas, 0, 0.0, "openai package missing"

    client = OpenAI(api_key=openai_api_key())
    model = openai_model()
    try:
        response = client.chat.completions.create(
            model=model,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You output strict JSON only for AppMap recommended test areas.",
                },
                {"role": "user", "content": prompt},
            ],
        )
    except Exception as exc:
        logger.warning("DiscoveryAgent test area LLM pass failed", extra={"error": str(exc)})
        return rule_areas, 0, 0.0, f"LLM error: {exc.__class__.__name__}"

    content = (response.choices[0].message.content or "").strip()
    try:
        parsed = _extract_json_object(content)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("DiscoveryAgent test area LLM returned invalid JSON", extra={"error": str(exc)})
        return rule_areas, 0, 0.0, "invalid LLM JSON"

    llm_areas = parsed.get("recommended_test_areas") if isinstance(parsed, dict) else None
    if not isinstance(llm_areas, list):
        return rule_areas, 0, 0.0, "invalid LLM JSON shape"

    usage = response.usage
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    tokens_used = prompt_tokens + completion_tokens
    cost = estimate_cost_usd(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, model=model)
    merged = _merge_llm_test_areas(rule_areas, llm_areas)
    return merged, tokens_used, cost, None


def attach_module_test_areas(
    modules: list[dict[str, Any]],
    recommended_test_areas: list[dict[str, Any]],
    *,
    per_module_limit: int = 5,
) -> list[dict[str, Any]]:
    """Attach a module-scoped slice for dashboard display."""
    enriched: list[dict[str, Any]] = []
    for module in modules:
        module_id = str(module.get("module_id") or "")
        scoped = [
            area
            for area in recommended_test_areas
            if str(area.get("module_id") or "") == module_id
        ][:per_module_limit]
        item = dict(module)
        if scoped:
            item["recommended_test_areas"] = scoped
        enriched.append(item)
    return enriched
