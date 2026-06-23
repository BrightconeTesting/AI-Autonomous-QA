"""Rule-based module tree and navigation graph for AppMap v3 (DISCOVERY-AGENT-VISION-SPEC §9.1)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from aqa_agents.discovery.flows import _module_key, _normalize_url
from aqa_shared.discovery.confidence import attach_confidence, rule_flow_confidence
from aqa_shared.llm.settings import estimate_cost_usd, llm_available, openai_api_key, openai_model

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "module-structure.v1.txt"
MAX_MODULES_DEFAULT = 40


def _slugify(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (label or "").strip().lower())
    return slug.strip("_") or "root"


def _path_segments(url: str) -> list[str]:
    path = urlparse(url or "").path
    parts = [part for part in path.split("/") if part and part.lower() != "index.php"]
    return [part.lower() for part in parts]


def _humanize_module_id(module_id: str) -> str:
    label = module_id.replace("-", " ").replace("_", " ").strip() or "Application"
    return label.title()


def _page_module_map(pages: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for page in pages:
        page_id = page.get("page_id")
        url = page.get("url") or ""
        if not page_id:
            continue
        mapping[str(page_id)] = _module_key(url)
    return mapping


def _flow_module_map(
    flows: list[dict[str, Any]], page_modules: dict[str, str]
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for flow in flows:
        flow_id = flow.get("flow_id")
        if not flow_id:
            continue
        module = flow.get("module")
        if module:
            mapping[str(flow_id)] = _slugify(str(module))
            continue
        for step in flow.get("steps") or []:
            if not isinstance(step, dict):
                continue
            page_id = step.get("page_id")
            if page_id and str(page_id) in page_modules:
                mapping[str(flow_id)] = page_modules[str(page_id)]
                break
    return mapping


def _infer_parent_module_id(
    module_id: str,
    page_urls: list[str],
    module_ids: set[str],
) -> str | None:
    for url in page_urls:
        parts = _path_segments(url)
        if module_id not in parts:
            continue
        idx = len(parts) - 1 - parts[::-1].index(module_id)
        if idx <= 0:
            continue
        candidate = _slugify(parts[idx - 1])
        if candidate in module_ids and candidate != module_id:
            return candidate
    return None


def _nav_parent_hints(
    elements: list[dict[str, Any]],
    pages: list[dict[str, Any]],
) -> dict[str, str]:
    """Map child module_id -> parent module_id from nav link labels (light heuristic)."""
    page_by_url = {_normalize_url(page.get("url") or ""): page for page in pages}
    page_modules = _page_module_map(pages)
    hints: dict[str, str] = {}

    nav_page_ids: set[str] = set()
    for element in elements:
        role = (element.get("role") or "").lower()
        tag = (element.get("tag_name") or "").lower()
        if role in {"navigation", "menubar", "menu"} or tag == "nav":
            page_id = element.get("page_id")
            if page_id:
                nav_page_ids.add(str(page_id))

    for element in elements:
        page_id = str(element.get("page_id") or "")
        if nav_page_ids and page_id not in nav_page_ids:
            continue
        tag = (element.get("tag_name") or "").lower()
        role = (element.get("role") or "").lower()
        if tag not in {"a", "link"} and role != "link":
            continue
        attrs = element.get("attributes") or {}
        href = attrs.get("href") or attrs.get("rawHref") or ""
        if not href or href.startswith("#"):
            continue
        resolved = _normalize_url(href)
        if not resolved.startswith("http"):
            source_page = next((p for p in pages if str(p.get("page_id")) == page_id), None)
            if source_page:
                resolved = _normalize_url(f"{source_page.get('url', '').rstrip('/')}/{href.lstrip('/')}")
        target_page = page_by_url.get(resolved)
        if target_page is None:
            continue
        source_module = page_modules.get(page_id)
        target_module = page_modules.get(str(target_page.get("page_id")))
        if not source_module or not target_module or source_module == target_module:
            continue
        if target_module not in hints:
            hints[target_module] = source_module
    return hints


def build_navigation_graph(
    pages: list[dict[str, Any]],
    discoveries: list[dict[str, Any]] | None,
    elements: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Light navigation graph from interaction discoveries and in-page links."""
    page_by_url = {_normalize_url(page.get("url") or ""): page for page in pages}
    edges: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_edge(edge: dict[str, Any]) -> None:
        key = json.dumps(edge, sort_keys=True, default=str)
        if key in seen:
            return
        seen.add(key)
        edges.append(edge)

    for discovery in discoveries or []:
        source_page_id = discovery.get("source_page_id")
        target_url = _normalize_url(discovery.get("url") or "")
        target_page = page_by_url.get(target_url)
        via = "interaction" if discovery.get("discovered_via") == "interaction" else "link"
        trigger = discovery.get("trigger_action") or {}
        label = trigger.get("text_content") or discovery.get("discovered_via")
        edge: dict[str, Any] = {
            "from_page_id": str(source_page_id) if source_page_id else None,
            "via": via,
            "label": str(label)[:120] if label else None,
        }
        if target_page:
            edge["to_page_id"] = str(target_page.get("page_id"))
        else:
            edge["to_url"] = discovery.get("url")
        add_edge(edge)

    for element in elements or []:
        attrs = element.get("attributes") or {}
        href = attrs.get("href") or ""
        if not href:
            continue
        tag = (element.get("tag_name") or "").lower()
        role = (element.get("role") or "").lower()
        if tag not in {"a", "link"} and role != "link":
            continue
        from_page_id = element.get("page_id")
        resolved = _normalize_url(href)
        if not resolved.startswith("http") and from_page_id:
            source = next((p for p in pages if str(p.get("page_id")) == str(from_page_id)), None)
            if source:
                base = source.get("url") or ""
                resolved = _normalize_url(f"{base.rstrip('/')}/{href.lstrip('/')}")
        target_page = page_by_url.get(resolved)
        if target_page is None or str(target_page.get("page_id")) == str(from_page_id):
            continue
        add_edge(
            {
                "from_page_id": str(from_page_id) if from_page_id else None,
                "to_page_id": str(target_page.get("page_id")),
                "via": "link",
                "label": (element.get("text_content") or "")[:120] or None,
            }
        )

    return edges


def build_modules_rule_pass(
    *,
    pages: list[dict[str, Any]],
    flows: list[dict[str, Any]],
    elements: list[dict[str, Any]] | None = None,
    discoveries: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build rule-based modules[] and navigation_graph."""
    if not pages:
        return [], build_navigation_graph(pages, discoveries, elements)

    page_modules = _page_module_map(pages)
    flow_modules = _flow_module_map(flows, page_modules)

    grouped_pages: dict[str, list[str]] = {}
    grouped_urls: dict[str, list[str]] = {}
    for page in pages:
        page_id = str(page.get("page_id"))
        module_id = page_modules.get(page_id, "root")
        grouped_pages.setdefault(module_id, []).append(page_id)
        grouped_urls.setdefault(module_id, []).append(page.get("url") or "")

    module_ids = set(grouped_pages.keys())
    nav_parents = _nav_parent_hints(elements or [], pages)

    modules: list[dict[str, Any]] = []
    for module_id in sorted(module_ids):
        page_ids = sorted(grouped_pages.get(module_id, []))
        parent = nav_parents.get(module_id) or _infer_parent_module_id(
            module_id, grouped_urls.get(module_id, []), module_ids
        )
        module_flows = [
            flow
            for flow in flows
            if flow_modules.get(str(flow.get("flow_id"))) == module_id
            or (
                not flow.get("flow_id")
                and flow.get("module")
                and _slugify(str(flow.get("module"))) == module_id
            )
        ]
        features = [
            {
                "name": str(flow.get("name") or "Flow")[:255],
                "flow_id": str(flow.get("flow_id")) if flow.get("flow_id") else None,
                "page_ids": sorted(
                    {
                        str(step.get("page_id"))
                        for step in (flow.get("steps") or [])
                        if isinstance(step, dict) and step.get("page_id")
                    }
                ),
            }
            for flow in module_flows
            if flow.get("flow_id")
        ]
        flow_ids = [str(f["flow_id"]) for f in features if f.get("flow_id")]

        confidence, factors = rule_flow_confidence()
        module = attach_confidence(
            {
                "module_id": module_id,
                "name": _humanize_module_id(module_id),
                "parent_module_id": parent,
                "pages": page_ids,
                "flow_ids": flow_ids,
                "features": features,
            },
            confidence=confidence,
            factors=[*factors, "rule:url_segment"],
        )
        modules.append(module)

    navigation_graph = build_navigation_graph(pages, discoveries, elements)
    return modules, navigation_graph


def _compact_modules(modules: list[dict[str, Any]], *, limit: int = 30) -> str:
    payload = [
        {
            "module_id": module.get("module_id"),
            "name": module.get("name"),
            "parent_module_id": module.get("parent_module_id"),
            "pages": module.get("pages") or [],
            "features": module.get("features") or [],
        }
        for module in modules[:limit]
    ]
    return json.dumps(payload, separators=(",", ":"))


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


def _compact_flows(flows: list[dict[str, Any]], *, limit: int = 40) -> str:
    payload = [
        {
            "flow_id": flow.get("flow_id"),
            "name": flow.get("name"),
            "module": flow.get("module"),
        }
        for flow in flows[:limit]
    ]
    return json.dumps(payload, separators=(",", ":"))


def _compact_navigation(navigation_graph: list[dict[str, Any]], *, limit: int = 40) -> str:
    return json.dumps(navigation_graph[:limit], separators=(",", ":"))


def load_module_prompt_template() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _render_module_prompt(
    *,
    rule_modules: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    flows: list[dict[str, Any]],
    navigation_graph: list[dict[str, Any]],
    max_modules: int,
) -> str:
    template = load_module_prompt_template()
    return (
        template.replace("{{max_modules}}", str(max_modules))
        .replace("{{rule_modules_json}}", _compact_modules(rule_modules))
        .replace("{{pages_json}}", _compact_pages(pages))
        .replace("{{flows_json}}", _compact_flows(flows))
        .replace("{{navigation_json}}", _compact_navigation(navigation_graph))
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


def validate_llm_modules(
    llm_modules: list[dict[str, Any]],
    *,
    rule_modules: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    flows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep LLM modules with grounded page_id and flow_id references."""
    page_ids = {str(page.get("page_id")) for page in pages if page.get("page_id")}
    flow_ids = {str(flow.get("flow_id")) for flow in flows if flow.get("flow_id")}
    rule_by_id = {str(m.get("module_id")): m for m in rule_modules if m.get("module_id")}
    allowed_module_ids = set(rule_by_id.keys())

    accepted: list[dict[str, Any]] = []
    for module in llm_modules:
        if not isinstance(module, dict):
            continue
        module_id = str(module.get("module_id") or "")
        if module_id not in allowed_module_ids:
            continue
        rule_module = rule_by_id[module_id]
        pages_in = module.get("pages") if isinstance(module.get("pages"), list) else rule_module.get("pages")
        if not pages_in or not all(str(pid) in page_ids for pid in pages_in):
            pages_in = rule_module.get("pages")

        features_in = module.get("features") if isinstance(module.get("features"), list) else []
        grounded_features: list[dict[str, Any]] = []
        for feature in features_in:
            if not isinstance(feature, dict):
                continue
            flow_id = feature.get("flow_id")
            if flow_id is not None and str(flow_id) not in flow_ids:
                continue
            page_refs = feature.get("page_ids") or []
            if page_refs and not all(str(pid) in page_ids for pid in page_refs):
                continue
            grounded_features.append(feature)

        if not grounded_features:
            grounded_features = list(rule_module.get("features") or [])

        parent = module.get("parent_module_id")
        if parent is not None and str(parent) not in allowed_module_ids:
            parent = rule_module.get("parent_module_id")

        confidence, factors = rule_flow_confidence(is_rule_based=False)
        accepted.append(
            attach_confidence(
                {
                    "module_id": module_id,
                    "name": str(module.get("name") or rule_module.get("name"))[:255],
                    "parent_module_id": parent,
                    "pages": list(pages_in or []),
                    "flow_ids": [
                        str(f["flow_id"])
                        for f in grounded_features
                        if isinstance(f, dict) and f.get("flow_id")
                    ],
                    "features": grounded_features,
                },
                confidence=confidence,
                factors=[*factors, "llm:grounding_passed"],
            )
        )

    if not accepted:
        return rule_modules

    accepted_ids = {m["module_id"] for m in accepted}
    for rule_module in rule_modules:
        if rule_module["module_id"] not in accepted_ids:
            accepted.append(rule_module)
    return sorted(accepted, key=lambda item: str(item.get("module_id")))


def structure_modules_with_llm(
    *,
    pages: list[dict[str, Any]],
    flows: list[dict[str, Any]],
    rule_modules: list[dict[str, Any]],
    navigation_graph: list[dict[str, Any]],
    use_llm: bool,
    token_budget_remaining: int,
    max_modules: int = MAX_MODULES_DEFAULT,
    llm_stage: str = "module_structure",
) -> tuple[list[dict[str, Any]], int, float, str | None]:
    """Return (modules, tokens_used, cost_estimate, skip_reason)."""
    if not rule_modules:
        return [], 0, 0.0, "no rule modules"
    if not use_llm:
        return rule_modules, 0, 0.0, "use_llm=false"
    if not llm_available(use_llm=True):
        return rule_modules, 0, 0.0, "OPENAI_API_KEY unset"
    if token_budget_remaining <= 0:
        return rule_modules, 0, 0.0, f"{llm_stage} budget exhausted"

    prompt = _render_module_prompt(
        rule_modules=rule_modules,
        pages=pages,
        flows=flows,
        navigation_graph=navigation_graph,
        max_modules=max_modules,
    )

    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai package not installed; skipping module LLM structuring")
        return rule_modules, 0, 0.0, "openai package missing"

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
                    "content": "You output strict JSON only for AppMap module tree structuring.",
                },
                {"role": "user", "content": prompt},
            ],
        )
    except Exception as exc:
        logger.warning(
            "DiscoveryAgent LLM module structuring failed; using rule-based modules",
            extra={"error": str(exc), "model": model},
        )
        return rule_modules, 0, 0.0, f"LLM error: {exc.__class__.__name__}"

    content = (response.choices[0].message.content or "").strip()
    try:
        parsed = _extract_json_object(content)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("DiscoveryAgent LLM returned invalid module JSON", extra={"error": str(exc)})
        return rule_modules, 0, 0.0, "invalid LLM JSON"

    raw_modules = parsed.get("modules") if isinstance(parsed, dict) else None
    if not isinstance(raw_modules, list):
        return rule_modules, 0, 0.0, "invalid LLM JSON shape"

    accepted = validate_llm_modules(
        raw_modules,
        rule_modules=rule_modules,
        pages=pages,
        flows=flows,
    )
    if accepted == rule_modules:
        return rule_modules, 0, 0.0, "LLM modules failed grounding"

    usage = response.usage
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    tokens_used = prompt_tokens + completion_tokens
    cost = estimate_cost_usd(
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, model=model
    )

    logger.info(
        "DiscoveryAgent LLM module structuring completed",
        extra={
            "ruleModuleCount": len(rule_modules),
            "llmModuleCount": len(accepted),
            "tokensUsed": tokens_used,
            "costEstimate": cost,
            "model": model,
        },
    )
    return accepted[:max_modules], tokens_used, cost, None
