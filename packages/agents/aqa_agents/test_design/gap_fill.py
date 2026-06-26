"""Optional LLM gap-fill for TestDesignAgent (Day 23, Phase D handoff)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from aqa_shared.llm.settings import estimate_cost_usd, llm_available, openai_api_key, openai_model

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "test-design.v1.txt"


def load_prompt_template() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _catalog_by_target(test_data_catalog: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for entry in test_data_catalog:
        target_type = str(entry.get("target_type") or "")
        target_id = str(entry.get("target_id") or "")
        if target_type and target_id:
            indexed[f"{target_type}:{target_id}"] = entry
    return indexed


def _safe_fill_values(test_data_catalog: list[dict[str, Any]]) -> dict[str, str]:
    values: dict[str, str] = {}
    for entry in test_data_catalog:
        for field in entry.get("fields") or []:
            name = str(field.get("name") or "").strip()
            suggested = str(field.get("suggested_safe_value") or "").strip()
            if name and suggested and suggested != "***":
                values[name.lower()] = suggested
    return values


def _high_confidence_mappings(api_ui_mappings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        mapping
        for mapping in api_ui_mappings
        if float(mapping.get("confidence") or 0) >= 0.7
    ]


def compact_appmap_for_prompt(appmap: dict[str, Any], *, max_pages: int = 40, max_elements: int = 150) -> str:
    pages = [
        {
            "page_id": page.get("page_id"),
            "url": page.get("url"),
            "title": page.get("title"),
        }
        for page in (appmap.get("pages") or [])[:max_pages]
    ]
    elements = [
        {
            "page_id": element.get("page_id"),
            "semantic_selector": element.get("semantic_selector"),
            "role": element.get("role"),
            "text_content": element.get("text_content"),
        }
        for element in (appmap.get("elements") or [])[:max_elements]
        if element.get("semantic_selector") or element.get("role")
    ]
    flows = [
        {
            "flow_id": flow.get("flow_id"),
            "name": flow.get("name"),
            "steps": flow.get("steps"),
        }
        for flow in (appmap.get("flows") or [])[:25]
    ]
    recommended = [
        {
            "area_id": area.get("area_id"),
            "area": area.get("area"),
            "priority": area.get("priority"),
            "priority_index": area.get("priority_index"),
            "rationale": area.get("rationale"),
            "signals": area.get("signals"),
            "form_id": area.get("form_id"),
            "api_endpoint_id": area.get("api_endpoint_id"),
        }
        for area in (appmap.get("recommended_test_areas") or [])[:20]
    ]
    mappings = [
        {
            "api_endpoint_id": mapping.get("api_endpoint_id"),
            "form_id": mapping.get("form_id"),
            "page_id": mapping.get("page_id"),
            "confidence": mapping.get("confidence"),
        }
        for mapping in _high_confidence_mappings(list(appmap.get("api_ui_mappings") or []))[:20]
    ]
    catalog = [
        {
            "target_type": entry.get("target_type"),
            "target_id": entry.get("target_id"),
            "fields": [
                {
                    "name": field.get("name"),
                    "suggested_safe_value": field.get("suggested_safe_value"),
                }
                for field in (entry.get("fields") or [])[:8]
            ],
        }
        for entry in (appmap.get("test_data_catalog") or [])[:15]
    ]
    compact = {
        "pages": pages,
        "elements": elements,
        "flows": flows,
        "recommended_test_areas": recommended,
        "api_ui_mappings": mappings,
        "test_data_catalog": catalog,
    }
    return json.dumps(compact, separators=(",", ":"))


def build_rule_cases_from_test_areas(
    appmap: dict[str, Any],
    *,
    rule_cases: list[dict[str, Any]],
    max_tests: int,
    priorities: list[str],
) -> list[dict[str, Any]]:
    """Generate grounded UI/API scenarios from DiscoveryAgent recommended_test_areas."""
    from aqa_agents.test_design.templates import generate_cases_from_recommended_areas

    generated = generate_cases_from_recommended_areas(
        appmap,
        max_tests=max_tests,
        priorities=priorities,
    )
    if not generated:
        return []
    existing_names = {_normalize_name(case.get("name")) for case in rule_cases}
    unique = [case for case in generated if _normalize_name(case.get("name")) not in existing_names]
    return unique


def _normalize_name(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _render_prompt(
    *,
    appmap: dict[str, Any],
    rule_cases: list[dict[str, Any]],
    max_tests: int,
    priorities: list[str],
) -> str:
    template = load_prompt_template()
    existing = json.dumps(
        [{"name": case.get("name"), "priority": case.get("priority")} for case in rule_cases[:30]],
        separators=(",", ":"),
    )
    areas_hint = ""
    areas = appmap.get("recommended_test_areas") or []
    if areas:
        areas_hint = (
            "\nPrioritize scenarios that cover recommended_test_areas (highest priority_index first). "
            "When a form_id and api_endpoint_id are linked in api_ui_mappings with confidence >= 0.7, "
            "propose paired UI + API validation scenarios. "
            "Use suggested_safe_value from test_data_catalog for fill steps when available."
        )
    return (
        template.replace("{{max_tests}}", str(max_tests))
        .replace("{{priorities}}", ", ".join(priorities))
        .replace("{{existing_rule_cases_json}}", existing)
        .replace("{{appmap_json}}", compact_appmap_for_prompt(appmap))
        + areas_hint
    )


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


def gap_fill_test_cases(
    appmap: dict[str, Any],
    *,
    rule_cases: list[dict[str, Any]],
    max_tests: int,
    priorities: list[str],
    use_llm: bool,
    token_budget_remaining: int,
) -> tuple[list[dict[str, Any]], int, float, str | None]:
    """Return (llm_cases, tokens_used, cost_estimate, skip_reason)."""
    area_cases = build_rule_cases_from_test_areas(
        appmap,
        rule_cases=rule_cases,
        max_tests=max(3, max_tests // 3),
        priorities=priorities,
    )

    if not use_llm:
        return area_cases, 0, 0.0, "use_llm=false"
    if not llm_available(use_llm=True):
        return area_cases, 0, 0.0, "OPENAI_API_KEY unset"
    if token_budget_remaining <= 0:
        return area_cases, 0, 0.0, "token budget exhausted"

    prompt = _render_prompt(
        appmap=appmap,
        rule_cases=[*rule_cases, *area_cases],
        max_tests=max_tests,
        priorities=priorities,
    )

    try:
        from openai import OpenAI
    except ImportError as exc:
        logger.warning("openai package not installed; skipping LLM gap-fill")
        return area_cases, 0, 0.0, "openai package missing"

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
                    "content": "You output strict JSON only for automated QA test case generation.",
                },
                {"role": "user", "content": prompt},
            ],
        )
    except Exception as exc:
        logger.warning(
            "TestDesignAgent LLM gap-fill failed; using rule-based cases only",
            extra={"error": str(exc), "model": model},
        )
        return area_cases, 0, 0.0, f"LLM error: {exc.__class__.__name__}"

    content = (response.choices[0].message.content or "").strip()
    try:
        parsed = _extract_json_object(content)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("TestDesignAgent LLM returned invalid JSON", extra={"error": str(exc)})
        return area_cases, 0, 0.0, "invalid LLM JSON"
    raw_cases = parsed.get("test_cases") if isinstance(parsed, dict) else None
    if not isinstance(raw_cases, list):
        logger.warning("LLM gap-fill returned no test_cases array")
        return area_cases, 0, 0.0, "invalid LLM JSON shape"

    usage = response.usage
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    tokens_used = prompt_tokens + completion_tokens
    cost = estimate_cost_usd(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, model=model)

    logger.info(
        "TestDesignAgent LLM gap-fill completed",
        extra={
            "llmCaseCount": len(raw_cases),
            "areaRuleCaseCount": len(area_cases),
            "tokensUsed": tokens_used,
            "costEstimate": cost,
            "model": model,
        },
    )
    return [*area_cases, *raw_cases], tokens_used, cost, None
