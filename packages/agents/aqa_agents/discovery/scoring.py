"""Rule-based scoring layer for AppMap v3 (DISCOVERY-AGENT-VISION-SPEC §9.5, §9.8)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

CRITICALITY_WEIGHTS = {
    "critical": 100,
    "high": 75,
    "medium": 50,
    "low": 25,
}

CRITICALITY_KEYWORDS = (
    "login",
    "signin",
    "sign-in",
    "dashboard",
    "checkout",
    "payment",
    "billing",
    "admin",
    "auth",
)

DESTRUCTIVE_KEYWORDS = (
    "delete",
    "remove",
    "cancel subscription",
    "destroy",
    "logout",
    "sign out",
)

PII_KEYWORDS = (
    "password",
    "ssn",
    "social security",
    "credit card",
    "card number",
    "cvv",
    "email",
    "phone",
)


from aqa_shared.testability.enrichment import score_element_testability


def _clamp_score(value: float) -> int:
    return max(0, min(100, int(round(value))))


def _flow_page_ids(flow: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for step in flow.get("steps") or []:
        if not isinstance(step, dict):
            continue
        page_id = step.get("page_id")
        if page_id:
            ids.add(str(page_id))
    return ids


def score_flow_risk(flow: dict[str, Any], elements_by_page: dict[str, list[dict[str, Any]]]) -> tuple[int, list[str]]:
    factors: list[str] = []
    score = 0.0
    name = str(flow.get("name") or "").lower()
    description = str(flow.get("description") or "").lower()
    blob = f"{name} {description}"

    if any(kw in blob for kw in DESTRUCTIVE_KEYWORDS):
        score += 25
        factors.append("destructive_ui")

    for step in flow.get("steps") or []:
        if not isinstance(step, dict):
            continue
        text = str(step.get("text_content") or "").lower()
        if any(kw in text for kw in DESTRUCTIVE_KEYWORDS):
            score += 15
            factors.append("destructive_step")
            break

    for page_id in _flow_page_ids(flow):
        for element in elements_by_page.get(page_id, []):
            text = str(element.get("text_content") or "").lower()
            if any(kw in text for kw in PII_KEYWORDS):
                score += 10
                factors.append("pii_fields")
                break

    if any(kw in blob for kw in ("login", "auth", "session", "signin")):
        score += 20
        factors.append("auth_session")

    return _clamp_score(score), sorted(set(factors))


def score_flow_complexity(flow: dict[str, Any]) -> tuple[int, list[str]]:
    factors: list[str] = []
    steps = [s for s in (flow.get("steps") or []) if isinstance(s, dict)]
    score = 0.0

    if len(steps) > 3:
        score += (len(steps) - 3) * 2
        factors.append(f"step_count={len(steps)}")

    page_ids = _flow_page_ids(flow)
    if len(page_ids) > 1:
        score += 15
        factors.append("multi_page_journey")

    urls = [str(s.get("url") or "") for s in steps if s.get("action") == "navigate"]
    if len(set(urls)) > 1 and any("#" in u for u in urls):
        score += 15
        factors.append("spa_url_variance")

    if any(kw in str(flow.get("name") or "").lower() for kw in DESTRUCTIVE_KEYWORDS):
        score += 10
        factors.append("destructive_teardown")

    for step in steps:
        action = str(step.get("action") or "")
        if action in {"select", "fill"} and step.get("value"):
            continue
        if action in {"upload", "attach"}:
            score += 8
            factors.append("file_upload")

    return _clamp_score(score), sorted(set(factors))


def infer_business_criticality(
    module: dict[str, Any],
    *,
    nav_index: int | None = None,
    overrides: dict[str, str] | None = None,
) -> str:
    module_id = str(module.get("module_id") or "")
    if overrides and module_id in overrides:
        return str(overrides[module_id]).lower()

    name = str(module.get("name") or module_id).lower()
    level = "medium"

    if nav_index is not None and nav_index < 3:
        level = "high"
    if any(kw in name or kw in module_id for kw in CRITICALITY_KEYWORDS):
        bump = {"low": "medium", "medium": "high", "high": "critical", "critical": "critical"}
        level = bump.get(level, "high")

    flow_count = len(module.get("flow_ids") or [])
    if flow_count >= 5:
        bump = {"low": "medium", "medium": "high", "high": "critical", "critical": "critical"}
        level = bump.get(level, level)

    return level


def compute_completeness_score(
    *,
    pages: list[dict[str, Any]],
    elements: list[dict[str, Any]],
    states: list[dict[str, Any]],
    modules: list[dict[str, Any]],
    crawl_config: dict[str, Any] | None = None,
    forms: list[dict[str, Any]] | None = None,
    api_endpoints: list[dict[str, Any]] | None = None,
    api_ui_mappings: list[dict[str, Any]] | None = None,
    spa_routes: list[dict[str, Any]] | None = None,
    data_entities: list[dict[str, Any]] | None = None,
    auth_detected: bool = False,
) -> tuple[int, list[str]]:
    """MVP completeness — score available dimensions; redistribute missing weights."""
    crawl_config = crawl_config or {}
    recommendations: list[str] = []
    dimensions: list[tuple[str, float, float]] = []

    max_pages = int(crawl_config.get("max_pages") or 50)
    page_coverage = min(100.0, (len(pages) / max(max_pages, 1)) * 100) if pages else 0.0
    dimensions.append(("page_coverage", 0.20, page_coverage))

    if states:
        states_by_page: dict[str, int] = {}
        for state in states:
            pid = str(state.get("page_id") or "")
            states_by_page[pid] = states_by_page.get(pid, 0) + 1
        deep_pages = sum(1 for count in states_by_page.values() if count >= 2)
        cic_depth = (deep_pages / max(len(states_by_page), 1)) * 100
        dimensions.append(("cic_depth", 0.20, cic_depth))
    else:
        recommendations.append("Enable CIC (cic_mode: full) for deeper interaction discovery")

    actionable = sum(
        1
        for el in elements
        if score_element_testability(el) >= 60
        and str(el.get("semantic_selector") or "").startswith(("getByRole", "getByLabel", "getByTestId"))
    )
    locator_quality = (actionable / max(len(elements), 1)) * 100 if elements else 0.0
    dimensions.append(("locator_quality", 0.15, locator_quality))

    if forms and api_ui_mappings is not None:
        mutating = [f for f in forms if str(f.get("method") or "get").lower() != "get"]
        mapped = sum(
            1
            for f in mutating
            if any(float(m.get("confidence") or 0) >= 0.7 for m in api_ui_mappings if m.get("form_id") == f.get("form_id"))
        )
        api_mapping = (mapped / max(len(mutating), 1)) * 100 if mutating else 100.0
        dimensions.append(("api_mapping", 0.15, api_mapping))
    elif api_endpoints:
        inventory_score = min(100.0, len(api_endpoints) * 5.0)
        dimensions.append(("api_inventory", 0.10, inventory_score))
    else:
        recommendations.append("Enable capture_network for API↔UI mapping (Track 2)")

    if spa_routes is not None:
        has_spa = any("#" in str(p.get("url") or "") for p in pages)
        if has_spa:
            spa_score = 100.0 if spa_routes else 0.0
            dimensions.append(("spa_routes", 0.10, spa_score))
            if not spa_routes:
                recommendations.append("Re-run with enable_pushstate_listener for SPA routes")
        else:
            dimensions.append(("spa_routes", 0.10, 100.0))

    if data_entities is not None:
        modules_with_entities = sum(
            1 for mod in modules if any(e.get("module_id") == mod.get("module_id") for e in data_entities)
        )
        entity_cov = (modules_with_entities / max(len(modules), 1)) * 100 if modules else 0.0
        dimensions.append(("entity_coverage", 0.10, entity_cov))
    else:
        recommendations.append("Entity inference available after Track 2 Phase C")

    if auth_detected:
        dimensions.append(("auth_clarity", 0.10, 100.0))
    else:
        login_pages = sum(
            1 for p in pages if any(kw in str(p.get("url") or "").lower() for kw in ("login", "signin", "auth"))
        )
        auth_score = 100.0 if login_pages else 50.0
        dimensions.append(("auth_clarity", 0.10, auth_score))

    total_weight = sum(weight for _, weight, _ in dimensions)
    if total_weight <= 0:
        return 0, recommendations

    weighted = sum((score * (weight / total_weight)) for _, weight, score in dimensions)
    return _clamp_score(weighted), recommendations


def apply_scoring(
    *,
    pages: list[dict[str, Any]],
    elements: list[dict[str, Any]],
    flows: list[dict[str, Any]],
    modules: list[dict[str, Any]],
    states: list[dict[str, Any]] | None = None,
    navigation_graph: list[dict[str, Any]] | None = None,
    crawl_config: dict[str, Any] | None = None,
    forms: list[dict[str, Any]] | None = None,
    api_endpoints: list[dict[str, Any]] | None = None,
    api_ui_mappings: list[dict[str, Any]] | None = None,
    data_entities: list[dict[str, Any]] | None = None,
    spa_routes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Score flows/modules and return scoring_summary + enriched modules/flows."""
    states = states or []
    elements_by_page: dict[str, list[dict[str, Any]]] = {}
    for element in elements:
        pid = str(element.get("page_id") or "")
        elements_by_page.setdefault(pid, []).append(element)

    scored_flows: list[dict[str, Any]] = []
    flow_scores: list[dict[str, Any]] = []
    for flow in flows:
        risk, risk_factors = score_flow_risk(flow, elements_by_page)
        complexity, complexity_factors = score_flow_complexity(flow)
        page_ids = _flow_page_ids(flow)
        module_elements = [el for pid in page_ids for el in elements_by_page.get(pid, [])]
        testability = (
            sum(score_element_testability(el) for el in module_elements) / len(module_elements)
            if module_elements
            else 50.0
        )
        enriched = dict(flow)
        enriched["risk_score"] = risk
        enriched["risk_factors"] = risk_factors
        enriched["automation_complexity_score"] = complexity
        enriched["complexity_factors"] = complexity_factors
        enriched["testability_score"] = _clamp_score(testability)
        scored_flows.append(enriched)
        flow_scores.append(enriched)

    nav_roots = _nav_module_order(navigation_graph or [], pages, modules)
    overrides = (crawl_config or {}).get("business_criticality_overrides") or {}

    scored_modules: list[dict[str, Any]] = []
    module_risks: list[int] = []
    module_testability: list[int] = []
    module_complexity: list[int] = []

    for index, module in enumerate(modules):
        module_id = str(module.get("module_id") or "")
        page_ids = [str(p) for p in (module.get("pages") or [])]
        module_elements = [el for pid in page_ids for el in elements_by_page.get(pid, [])]
        module_flows = [
            f for f in scored_flows if str(f.get("flow_id")) in {str(x) for x in (module.get("flow_ids") or [])}
        ]

        testability = (
            sum(score_element_testability(el) for el in module_elements) / len(module_elements)
            if module_elements
            else 50.0
        )
        risk = max((f.get("risk_score", 0) for f in module_flows), default=0)
        if module_elements:
            destructive_hits = sum(
                1
                for el in module_elements
                if any(kw in str(el.get("text_content") or "").lower() for kw in DESTRUCTIVE_KEYWORDS)
            )
            if destructive_hits:
                risk = max(risk, min(100, 20 + destructive_hits * 10))

        complexity_vals = [f.get("automation_complexity_score", 0) for f in module_flows]
        complexity = int(sum(complexity_vals) / len(complexity_vals)) if complexity_vals else 30

        risk_factors = sorted(
            {factor for f in module_flows for factor in (f.get("risk_factors") or [])}
        )
        complexity_factors = sorted(
            {factor for f in module_flows for factor in (f.get("complexity_factors") or [])}
        )

        nav_index = nav_roots.index(module_id) if module_id in nav_roots else None
        criticality = infer_business_criticality(
            module, nav_index=nav_index, overrides=overrides if isinstance(overrides, dict) else None
        )

        enriched = dict(module)
        enriched["risk_score"] = _clamp_score(risk)
        enriched["risk_factors"] = risk_factors
        enriched["testability_score"] = _clamp_score(testability)
        enriched["automation_complexity_score"] = _clamp_score(complexity)
        enriched["complexity_factors"] = complexity_factors
        enriched["business_criticality"] = criticality
        scored_modules.append(enriched)

        module_risks.append(enriched["risk_score"])
        module_testability.append(enriched["testability_score"])
        module_complexity.append(enriched["automation_complexity_score"])

    auth_detected = any(
        any(kw in str(p.get("url") or "").lower() for kw in ("login", "signin", "auth"))
        for p in pages
    )
    completeness, recommendations = compute_completeness_score(
        pages=pages,
        elements=elements,
        states=states,
        modules=scored_modules,
        crawl_config=crawl_config,
        auth_detected=auth_detected,
        forms=forms,
        api_endpoints=api_endpoints,
        api_ui_mappings=api_ui_mappings,
        data_entities=data_entities,
        spa_routes=spa_routes,
    )

    top_risk = sorted(
        [
            {
                "module_id": m["module_id"],
                "name": m.get("name"),
                "risk_score": m.get("risk_score", 0),
                "top_factor": (m.get("risk_factors") or ["unknown"])[0],
            }
            for m in scored_modules
        ],
        key=lambda item: item["risk_score"],
        reverse=True,
    )[:5]

    scoring_summary = {
        "app_risk_score": _clamp_score(sum(module_risks) / len(module_risks)) if module_risks else 0,
        "app_testability_score": _clamp_score(sum(module_testability) / len(module_testability))
        if module_testability
        else 0,
        "app_automation_complexity_score": _clamp_score(
            sum(module_complexity) / len(module_complexity)
        )
        if module_complexity
        else 0,
        "discovery_completeness_score": completeness,
        "high_risk_modules": [m["module_id"] for m in top_risk if m["risk_score"] >= 60],
        "top_risk_modules": top_risk,
        "recommendations": recommendations,
    }

    return {
        "modules": scored_modules,
        "flows": scored_flows,
        "scoring_summary": scoring_summary,
        "discovery_completeness_score": completeness,
        "recommendations": recommendations,
    }


def _nav_module_order(
    navigation_graph: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    modules: list[dict[str, Any]],
) -> list[str]:
    """Approximate top-nav module order from early navigation edges."""
    page_to_module = {}
    for mod in modules:
        for page_id in mod.get("pages") or []:
            page_to_module[str(page_id)] = str(mod.get("module_id"))

    ordered: list[str] = []
    seen: set[str] = set()
    for edge in navigation_graph:
        to_page = edge.get("to_page_id")
        if not to_page:
            continue
        mod_id = page_to_module.get(str(to_page))
        if mod_id and mod_id not in seen:
            seen.add(mod_id)
            ordered.append(mod_id)

    for mod in modules:
        mid = str(mod.get("module_id"))
        if mid not in seen:
            ordered.append(mid)
    return ordered
