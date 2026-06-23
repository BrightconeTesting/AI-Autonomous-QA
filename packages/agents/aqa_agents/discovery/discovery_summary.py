"""Build dashboard-oriented discovery summary from AppMap data (DISCOVERY-AGENT-VISION-SPEC §10.3)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


def _page_label(page: dict[str, Any]) -> str:
    title = str(page.get("title") or "").strip()
    if title:
        return title
    path = urlparse(str(page.get("url") or "")).path.rstrip("/")
    if path:
        segment = path.split("/")[-1] or path
        return segment.replace("-", " ").replace("_", " ").title()
    return str(page.get("url") or "Page")


def _element_counts(elements: list[dict[str, Any]]) -> dict[str, int]:
    buttons = 0
    links = 0
    form_tags = 0
    form_pages: set[str] = set()

    for element in elements:
        tag = str(element.get("tag_name") or "").lower()
        role = str(element.get("role") or "").lower()
        page_id = str(element.get("page_id") or "")

        if tag == "button" or role == "button":
            buttons += 1
        if tag == "a" or role == "link":
            links += 1
        if tag == "form":
            form_tags += 1
            if page_id:
                form_pages.add(page_id)
        elif role in {"textbox", "combobox", "checkbox", "radio"} and page_id:
            form_pages.add(page_id)

    return {
        "buttons": buttons,
        "links": links,
        "form_tags": form_tags,
        "form_pages": len(form_pages),
    }


def _what_forms_exist(
    pages: list[dict[str, Any]],
    elements: list[dict[str, Any]],
) -> list[dict[str, str]]:
    page_by_id = {str(page.get("page_id")): page for page in pages}
    forms: list[dict[str, str]] = []
    seen_pages: set[str] = set()

    for element in elements:
        tag = str(element.get("tag_name") or "").lower()
        role = str(element.get("role") or "").lower()
        page_id = str(element.get("page_id") or "")
        if not page_id or page_id in seen_pages:
            continue
        is_form = tag == "form" or role in {"textbox", "combobox", "checkbox", "radio"}
        if not is_form:
            continue
        page = page_by_id.get(page_id)
        if page is None:
            continue
        seen_pages.add(page_id)
        page_name = _page_label(page)
        forms.append({"name": f"{page_name} form", "page": page_name})

    return sorted(forms, key=lambda item: (item["page"], item["name"]))


def _what_forms_exist_from_records(
    pages: list[dict[str, Any]],
    forms: list[dict[str, Any]],
) -> list[dict[str, str]]:
    page_by_id = {str(page.get("page_id")): page for page in pages}
    output: list[dict[str, str]] = []
    for form in forms:
        page = page_by_id.get(str(form.get("page_id") or ""))
        page_name = _page_label(page) if page else "Page"
        output.append(
            {
                "name": str(form.get("name") or "Form"),
                "page": page_name,
            }
        )
    return sorted(output, key=lambda item: (item["page"], item["name"]))


def _build_module_tree(modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not modules:
        return []

    roots = [module for module in modules if not module.get("parent_module_id")]
    if not roots:
        roots = list(modules)

    tree: list[dict[str, Any]] = []
    for module in roots:
        module_id = str(module.get("module_id") or "")
        children: list[str] = []

        for child in modules:
            if str(child.get("parent_module_id") or "") == module_id:
                child_name = str(child.get("name") or child.get("module_id") or "")
                if child_name:
                    children.append(child_name)

        for feature in module.get("features") or []:
            if not isinstance(feature, dict):
                continue
            feature_name = str(feature.get("name") or "").strip()
            if feature_name and feature_name not in children:
                children.append(feature_name)

        tree.append(
            {
                "name": str(module.get("name") or module_id or "Module"),
                "children": children,
            }
        )
    return tree


def _what_should_be_tested_first(
    modules: list[dict[str, Any]],
    flows: list[dict[str, Any]],
    scoring_summary: dict[str, Any] | None,
) -> list[str]:
    priorities: list[str] = []
    seen: set[str] = set()

    top_risk = list((scoring_summary or {}).get("top_risk_modules") or [])
    module_by_id = {str(module.get("module_id")): module for module in modules}
    flow_by_id = {str(flow.get("flow_id")): flow for flow in flows}

    for item in top_risk:
        module_id = str(item.get("module_id") or "")
        module = module_by_id.get(module_id)
        module_name = str(item.get("name") or (module or {}).get("name") or module_id)
        if module_name and module_name not in seen:
            seen.add(module_name)
            priorities.append(module_name)

        if module:
            for flow_id in module.get("flow_ids") or []:
                flow = flow_by_id.get(str(flow_id))
                if not flow:
                    continue
                flow_name = str(flow.get("name") or "")
                if flow_name and flow_name not in seen:
                    seen.add(flow_name)
                    priorities.append(flow_name)

    for module in sorted(modules, key=lambda mod: int(mod.get("risk_score") or 0), reverse=True):
        name = str(module.get("name") or "")
        if name and name not in seen:
            seen.add(name)
            priorities.append(name)
        if len(priorities) >= 8:
            break

    return priorities[:8]


def _auth_summary(
    pages: list[dict[str, Any]],
    auth_config: dict[str, Any] | None,
    auth_intelligence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    auth_intelligence = auth_intelligence or {}
    if auth_intelligence:
        personas = [
            str(persona.get("persona_id") or "")
            for persona in (auth_intelligence.get("personas") or [])
            if persona.get("authenticated")
        ]
        return {
            "session_type": str(auth_intelligence.get("session_type") or "unknown"),
            "personas_authenticated": personas,
            "login_detected": bool(
                auth_intelligence.get("login_flow_id")
                or auth_intelligence.get("login_api_endpoint_id")
            ),
            "blocker_count": len(auth_intelligence.get("blockers") or []),
        }

    auth_detected = any(
        any(kw in str(page.get("url") or "").lower() for kw in ("login", "signin", "auth"))
        for page in pages
    )
    session_type = "unknown"
    personas: list[str] = []

    if auth_config:
        session_type = str(auth_config.get("type") or "form")
        if auth_config.get("credentials") or auth_config.get("credentials_secret_ref") or auth_config.get("cookies"):
            personas.append("default")
    elif auth_detected:
        session_type = "form"

    return {
        "session_type": session_type,
        "personas_authenticated": personas,
    }


def build_discovery_summary(
    appmap: dict[str, Any],
    *,
    auth_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive §10.3 discovery summary from a loaded AppMap document."""
    pages = list(appmap.get("pages") or [])
    elements = list(appmap.get("elements") or [])
    flows = list(appmap.get("flows") or [])
    modules = list(appmap.get("modules") or [])
    discoveries = list(appmap.get("discoveries") or appmap.get("page_discoveries") or [])
    scoring_summary = appmap.get("scoring_summary") if isinstance(appmap.get("scoring_summary"), dict) else {}

    forms = list(appmap.get("forms") or [])
    element_counts = _element_counts(elements)
    api_endpoints = list(appmap.get("api_endpoints") or [])
    data_entities = list(appmap.get("data_entities") or appmap.get("entities") or [])
    api_dependency_edges = list((appmap.get("api_dependency_graph") or {}).get("edges") or [])
    if not api_dependency_edges:
        api_dependency_edges = list(appmap.get("api_dependency_edges") or [])
    test_data_catalog = list(appmap.get("test_data_catalog") or [])
    auth_intelligence = appmap.get("auth_intelligence") if isinstance(appmap.get("auth_intelligence"), dict) else {}
    spa_routes = list(appmap.get("spa_routes") or [])

    top_risk_areas = [
        {
            "module": str(item.get("name") or item.get("module_id") or ""),
            "risk_score": int(item.get("risk_score") or 0),
            "top_factor": str(item.get("top_factor") or "unknown"),
        }
        for item in (scoring_summary.get("top_risk_modules") or [])
        if item.get("name") or item.get("module_id")
    ]

    recommendations = list(appmap.get("recommendations") or scoring_summary.get("recommendations") or [])

    return {
        "application_id": str(appmap.get("application_id") or ""),
        "last_crawl_at": appmap.get("last_crawl_at"),
        "schema_version": int(appmap.get("schema_version") or 1),
        "counts": {
            "pages": len(pages),
            "buttons": element_counts["buttons"],
            "forms": len(forms) if forms else max(element_counts["form_tags"], element_counts["form_pages"]),
            "links": element_counts["links"],
            "api_endpoints": len(api_endpoints),
            "flows": len(flows),
            "entities": len(data_entities),
            "modules": len(modules),
            "spa_routes": len(spa_routes) if spa_routes else len(discoveries),
            "api_dependency_edges": len(api_dependency_edges),
            "test_data_catalog": len(test_data_catalog),
        },
        "scoring_summary": scoring_summary,
        "discovery_completeness_score": int(
            appmap.get("discovery_completeness_score")
            or scoring_summary.get("discovery_completeness_score")
            or 0
        ),
        "recommendations": recommendations,
        "what_pages_exist": sorted({_page_label(page) for page in pages}),
        "what_forms_exist": _what_forms_exist_from_records(pages, forms)
        if forms
        else _what_forms_exist(pages, elements),
        "what_apis_are_called": [
            {"method": str(item.get("method") or "GET"), "path": str(item.get("path") or item.get("url") or "")}
            for item in api_endpoints
            if item.get("path") or item.get("url")
        ],
        "what_should_be_tested_first": _what_should_be_tested_first(modules, flows, scoring_summary),
        "top_risk_areas": top_risk_areas,
        "module_tree": _build_module_tree(modules),
        "auth_summary": _auth_summary(pages, auth_config, auth_intelligence),
    }
