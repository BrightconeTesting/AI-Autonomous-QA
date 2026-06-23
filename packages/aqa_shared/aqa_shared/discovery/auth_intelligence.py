"""Authentication intelligence assembly (DISCOVERY-AGENT-VISION-SPEC §8.9)."""

from __future__ import annotations

from typing import Any

_AUTH_PATH_KEYWORDS = ("login", "auth", "token", "session", "oauth", "signin", "sign-in")
_BEARER_HEADER_KEYWORDS = ("authorization", "bearer")
_LOGIN_FORM_KEYWORDS = ("password", "login", "signin", "sign-in")


def _is_auth_endpoint(endpoint: dict[str, Any]) -> bool:
    blob = f"{endpoint.get('path_pattern') or ''} {endpoint.get('path') or ''}".lower()
    return any(keyword in blob for keyword in _AUTH_PATH_KEYWORDS)


def _is_login_page(page: dict[str, Any], forms: list[dict[str, Any]], elements: list[dict[str, Any]]) -> bool:
    url = str(page.get("url") or "").lower()
    title = str(page.get("title") or "").lower()
    if any(keyword in url or keyword in title for keyword in _LOGIN_FORM_KEYWORDS):
        return True
    page_id = str(page.get("page_id") or "")
    page_forms = [form for form in forms if str(form.get("page_id") or "") == page_id]
    for form in page_forms:
        attrs = form.get("attributes") or {}
        if "password" in str(attrs).lower() or "login" in str(attrs.get("name") or "").lower():
            return True
    page_elements = [element for element in elements if str(element.get("page_id") or "") == page_id]
    for element in page_elements:
        attrs = element.get("attributes") or {}
        if str(attrs.get("type") or "").lower() == "password":
            return True
        if "password" in str(attrs.get("name") or "").lower():
            return True
    return False


def _detect_session_type(
    *,
    api_endpoints: list[dict[str, Any]],
    auth_signals: dict[str, Any] | None,
) -> str:
    auth_signals = auth_signals or {}
    if auth_signals.get("session_type"):
        return str(auth_signals["session_type"])
    has_bearer = any(
        any(keyword in str(header).lower() for keyword in _BEARER_HEADER_KEYWORDS)
        for endpoint in api_endpoints
        for header in (endpoint.get("request_headers") or {}).keys()
    )
    has_cookie = bool(auth_signals.get("cookie_names"))
    if has_bearer and has_cookie:
        return "mixed"
    if has_bearer:
        return "bearer"
    return "cookie"


def build_auth_intelligence(
    *,
    pages: list[dict[str, Any]],
    forms: list[dict[str, Any]],
    flows: list[dict[str, Any]],
    elements: list[dict[str, Any]],
    api_endpoints: list[dict[str, Any]],
    modules: list[dict[str, Any]],
    persona_visibility: dict[str, Any] | None = None,
    auth_signals: dict[str, Any] | None = None,
    crawl_authenticated: bool = False,
) -> dict[str, Any]:
    """Build AppMap auth_intelligence from crawl signals and persona visibility."""
    auth_signals = dict(auth_signals or {})
    persona_visibility = persona_visibility or {}

    login_page_ids = [
        str(page.get("page_id"))
        for page in pages
        if page.get("page_id") and _is_login_page(page, forms, elements)
    ]
    login_api_ids = [
        str(endpoint.get("endpoint_id"))
        for endpoint in api_endpoints
        if endpoint.get("endpoint_id") and _is_auth_endpoint(endpoint)
    ]
    protected_page_ids = list(
        dict.fromkeys(
            [
                str(page_id)
                for page_id in (auth_signals.get("protected_page_ids") or [])
                if page_id
            ]
        )
    )
    protected_api_ids = []
    for endpoint in api_endpoints:
        endpoint_id = str(endpoint.get("endpoint_id") or "")
        if not endpoint_id:
            continue
        key = f"{str(endpoint.get('method') or 'GET').upper()} {endpoint.get('path_pattern') or ''}"
        if key in [str(item) for item in (auth_signals.get("protected_api_endpoint_ids") or [])]:
            protected_api_ids.append(endpoint_id)
    protected_api_ids = list(dict.fromkeys(protected_api_ids))

    login_flow_id = None
    for flow in flows:
        steps = flow.get("steps") or []
        for step in steps:
            if str(step.get("page_id") or "") in login_page_ids:
                login_flow_id = str(flow.get("flow_id") or "")
                break
        if login_flow_id:
            break

    personas = build_persona_auth_rows(
        modules=modules,
        persona_visibility=persona_visibility,
        default_authenticated=crawl_authenticated or bool(auth_signals.get("authenticated")),
    )
    visibility_matrix = persona_visibility.get("visibility_matrix") or {}
    if not visibility_matrix and persona_visibility.get("personas"):
        from aqa_shared.discovery.persona_merge import build_visibility_matrix

        visibility_matrix = build_visibility_matrix(
            modules=modules, persona_visibility=persona_visibility
        )

    blockers = list(auth_signals.get("blockers") or [])
    if auth_signals.get("halt_reason"):
        blocker_type = "mfa" if "mfa" in str(auth_signals["halt_reason"]).lower() else "captcha"
        if "captcha" in str(auth_signals["halt_reason"]).lower():
            blocker_type = "captcha"
        blockers.append(
            {
                "type": blocker_type,
                "page_url": auth_signals.get("halt_url"),
                "message": auth_signals.get("halt_reason"),
            }
        )

    return {
        "session_type": _detect_session_type(api_endpoints=api_endpoints, auth_signals=auth_signals),
        "login_flow_id": login_flow_id,
        "login_api_endpoint_id": login_api_ids[0] if login_api_ids else None,
        "protected_page_ids": protected_page_ids,
        "protected_api_endpoint_ids": protected_api_ids,
        "cookie_names": list(auth_signals.get("cookie_names") or []),
        "storage_keys": list(auth_signals.get("storage_keys") or []),
        "personas": personas,
        "visibility_matrix": visibility_matrix,
        "blockers": blockers,
        "authenticated": crawl_authenticated or bool(auth_signals.get("authenticated")),
    }


def build_persona_auth_rows(
    *,
    modules: list[dict[str, Any]],
    persona_visibility: dict[str, Any],
    default_authenticated: bool,
) -> list[dict[str, Any]]:
    from aqa_shared.discovery.persona_merge import build_visibility_matrix

    matrix = persona_visibility.get("visibility_matrix")
    if not matrix:
        matrix = build_visibility_matrix(modules=modules, persona_visibility=persona_visibility)

    rows: list[dict[str, Any]] = []
    for persona in persona_visibility.get("personas") or []:
        persona_id = str(persona.get("persona_id") or "")
        if not persona_id:
            continue
        visible_module_ids = list((matrix.get(persona_id) or {}).get("visible_module_ids") or [])
        exclusive_module_ids = list((matrix.get(persona_id) or {}).get("exclusive_module_ids") or [])
        rows.append(
            {
                "persona_id": persona_id,
                "label": persona.get("label"),
                "authenticated": bool(persona.get("authenticated", default_authenticated)),
                "visible_module_ids": visible_module_ids,
                "exclusive_module_ids": exclusive_module_ids,
            }
        )

    if not rows and default_authenticated:
        module_ids = [str(module.get("module_id") or "") for module in modules if module.get("module_id")]
        rows.append(
            {
                "persona_id": "default",
                "label": "Default",
                "authenticated": True,
                "visible_module_ids": module_ids,
                "exclusive_module_ids": [],
            }
        )
    return rows
