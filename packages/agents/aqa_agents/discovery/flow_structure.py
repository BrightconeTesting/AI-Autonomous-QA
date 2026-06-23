"""Optional LLM flow structuring for DiscoveryAgent (SPEC §17.1, §31.6)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from aqa_shared.llm.settings import estimate_cost_usd, llm_available, openai_api_key, openai_model
from aqa_shared.discovery.confidence import attach_confidence, llm_grounded_flow_confidence, rule_flow_confidence

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "flow-structure.v1.txt"
MAX_FLOWS_DEFAULT = 50


def load_prompt_template() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _compact_pages(pages: list[dict[str, Any]], *, limit: int = 40) -> str:
    payload = [
        {
            "page_id": page.get("page_id"),
            "url": page.get("url"),
            "title": page.get("title"),
        }
        for page in pages[:limit]
    ]
    return json.dumps(payload, separators=(",", ":"))


def _compact_elements(elements: list[dict[str, Any]], *, limit: int = 120) -> str:
    payload = [
        {
            "page_id": element.get("page_id"),
            "semantic_selector": element.get("semantic_selector"),
            "role": element.get("role"),
            "text_content": element.get("text_content"),
        }
        for element in elements[:limit]
        if element.get("semantic_selector") or element.get("role")
    ]
    return json.dumps(payload, separators=(",", ":"))


def _compact_rule_flows(flows: list[dict[str, Any]], *, limit: int = 30) -> str:
    payload = [
        {
            "name": flow.get("name"),
            "description": flow.get("description"),
            "module": flow.get("module"),
            "steps": flow.get("steps") or [],
        }
        for flow in flows[:limit]
    ]
    return json.dumps(payload, separators=(",", ":"))


def _render_prompt(
    *,
    pages: list[dict[str, Any]],
    elements: list[dict[str, Any]],
    rule_flows: list[dict[str, Any]],
    max_flows: int,
) -> str:
    template = load_prompt_template()
    return (
        template.replace("{{max_flows}}", str(max_flows))
        .replace("{{rule_flows_json}}", _compact_rule_flows(rule_flows))
        .replace("{{pages_json}}", _compact_pages(pages))
        .replace("{{elements_json}}", _compact_elements(elements))
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


def _normalize_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def _collect_grounding(
    pages: list[dict[str, Any]], elements: list[dict[str, Any]]
) -> tuple[set[str], set[str], set[str]]:
    page_ids = {str(page.get("page_id")) for page in pages if page.get("page_id")}
    urls = {_normalize_url(str(page.get("url") or "")) for page in pages if page.get("url")}
    selectors = {
        str(element.get("semantic_selector")).strip()
        for element in elements
        if element.get("semantic_selector")
    }
    return page_ids, urls, selectors


def _step_allowed(
    step: dict[str, Any],
    *,
    page_ids: set[str],
    urls: set[str],
    selectors: set[str],
    allowed_step_sigs: set[str],
) -> bool:
    sig = json.dumps(step, sort_keys=True, default=str)
    if sig in allowed_step_sigs:
        return True

    action = str(step.get("action") or "")
    if action == "navigate":
        page_id = step.get("page_id")
        url = _normalize_url(str(step.get("url") or ""))
        if page_id is not None and str(page_id) in page_ids:
            return True
        if url and (url in urls or any(url.startswith(u) for u in urls if u)):
            return True
        return False

    selector = str(step.get("semantic_selector") or "").strip()
    if selector and (selector in selectors or any(selector in item for item in selectors)):
        return True
    return False


def _annotate_rule_flows(flows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for flow in flows:
        confidence, factors = rule_flow_confidence()
        annotated.append(attach_confidence(dict(flow), confidence=confidence, factors=factors))
    return annotated


def validate_llm_flows(
    llm_flows: list[dict[str, Any]],
    *,
    rule_flows: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    elements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep LLM flows whose steps are grounded in rule flows or AppMap."""
    page_ids, urls, selectors = _collect_grounding(pages, elements)
    allowed_step_sigs = {
        json.dumps(step, sort_keys=True, default=str)
        for flow in rule_flows
        for step in (flow.get("steps") or [])
        if isinstance(step, dict)
    }

    accepted: list[dict[str, Any]] = []
    for flow in llm_flows:
        if not isinstance(flow, dict):
            continue
        steps = flow.get("steps") or []
        if not steps or not isinstance(steps, list):
            continue
        if not all(
            isinstance(step, dict)
            and _step_allowed(
                step,
                page_ids=page_ids,
                urls=urls,
                selectors=selectors,
                allowed_step_sigs=allowed_step_sigs,
            )
            for step in steps
        ):
            continue
        confidence, factors = llm_grounded_flow_confidence(accepted_count=len(accepted) + 1)
        accepted.append(
            attach_confidence(
                {
                    "name": str(flow.get("name") or "Unnamed flow")[:255],
                    "description": flow.get("description"),
                    "steps": steps,
                    "source": "crawler",
                    "module": flow.get("module"),
                },
                confidence=confidence,
                factors=factors,
            )
        )
    return accepted


def structure_flows_with_llm(
    *,
    pages: list[dict[str, Any]],
    elements: list[dict[str, Any]],
    rule_flows: list[dict[str, Any]],
    use_llm: bool,
    token_budget_remaining: int,
    max_flows: int = MAX_FLOWS_DEFAULT,
    llm_stage: str = "flow_structure",
) -> tuple[list[dict[str, Any]], int, float, str | None]:
    """Return (flows, tokens_used, cost_estimate, skip_reason)."""
    annotated_rules = _annotate_rule_flows(rule_flows)
    if not rule_flows:
        return [], 0, 0.0, "no rule flows"
    if not use_llm:
        return annotated_rules, 0, 0.0, "use_llm=false"
    if not llm_available(use_llm=True):
        return annotated_rules, 0, 0.0, "OPENAI_API_KEY unset"
    if token_budget_remaining <= 0:
        return annotated_rules, 0, 0.0, f"{llm_stage} budget exhausted"

    prompt = _render_prompt(
        pages=pages,
        elements=elements,
        rule_flows=rule_flows,
        max_flows=max_flows,
    )

    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai package not installed; skipping discovery LLM flow structuring")
        return annotated_rules, 0, 0.0, "openai package missing"

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
                    "content": "You output strict JSON only for AppMap user-journey flow structuring.",
                },
                {"role": "user", "content": prompt},
            ],
        )
    except Exception as exc:
        logger.warning(
            "DiscoveryAgent LLM flow structuring failed; using rule-based flows",
            extra={"error": str(exc), "model": model},
        )
        return annotated_rules, 0, 0.0, f"LLM error: {exc.__class__.__name__}"

    content = (response.choices[0].message.content or "").strip()
    try:
        parsed = _extract_json_object(content)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("DiscoveryAgent LLM returned invalid JSON", extra={"error": str(exc)})
        return annotated_rules, 0, 0.0, "invalid LLM JSON"

    raw_flows = parsed.get("flows") if isinstance(parsed, dict) else None
    if not isinstance(raw_flows, list):
        return annotated_rules, 0, 0.0, "invalid LLM JSON shape"

    accepted = validate_llm_flows(
        raw_flows,
        rule_flows=rule_flows,
        pages=pages,
        elements=elements,
    )
    if not accepted:
        logger.info("DiscoveryAgent LLM flows rejected; keeping rule-based flows")
        return annotated_rules, 0, 0.0, "LLM flows failed grounding"

    usage = response.usage
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    tokens_used = prompt_tokens + completion_tokens
    cost = estimate_cost_usd(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, model=model)

    logger.info(
        "DiscoveryAgent LLM flow structuring completed",
        extra={
            "ruleFlowCount": len(rule_flows),
            "llmFlowCount": len(accepted),
            "tokensUsed": tokens_used,
            "costEstimate": cost,
            "model": model,
        },
    )
    return accepted[:max_flows], tokens_used, cost, None
