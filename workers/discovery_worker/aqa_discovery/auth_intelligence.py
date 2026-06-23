"""Collect authentication signals during crawl (DISCOVERY-AGENT-VISION-SPEC §8.9)."""

from __future__ import annotations

from typing import Any

from aqa_discovery.api_types import ApiEndpointSnapshot
from aqa_discovery.types import PageSnapshot

_AUTH_PATH_KEYWORDS = ("login", "auth", "token", "session", "oauth", "signin", "sign-in")


def _has_password_field(page: PageSnapshot) -> bool:
    for element in page.elements:
        attrs = element.attributes or {}
        if str(attrs.get("type") or "").lower() == "password":
            return True
        if "password" in str(attrs.get("name") or "").lower():
            return True
    for state in page.states:
        for element in state.elements:
            attrs = element.attributes or {}
            if str(attrs.get("type") or "").lower() == "password":
                return True
    return False


def _is_auth_endpoint_snapshot(endpoint: ApiEndpointSnapshot) -> bool:
    blob = f"{endpoint.path_pattern} {endpoint.path}".lower()
    return any(keyword in blob for keyword in _AUTH_PATH_KEYWORDS)


def collect_auth_signals_from_crawl(
    *,
    pages: list[PageSnapshot],
    api_endpoints: list[ApiEndpointSnapshot],
    authenticated: bool,
    persona_id: str | None = None,
    halt_reason: str | None = None,
    halt_url: str | None = None,
) -> dict[str, Any]:
    """Summarize auth-related observations without storing secrets."""
    protected_page_ids: list[str] = []
    protected_api_endpoint_ids: list[str] = []
    cookie_names: set[str] = set()
    blockers: list[dict[str, Any]] = []

    for page in pages:
        if page.status in {401, 403}:
            protected_page_ids.append(page.url)

    for endpoint in api_endpoints:
        if endpoint.status in {401, 403}:
            protected_api_endpoint_ids.append(f"{endpoint.method} {endpoint.path_pattern}")
        for header in endpoint.request_headers or {}:
            if header.lower() == "authorization":
                pass
            if header.lower() == "cookie":
                pass
        for header, _value in (endpoint.request_headers or {}).items():
            if header.lower() == "cookie":
                cookie_names.add("session")

    login_detected = any(_has_password_field(page) for page in pages) or any(
        _is_auth_endpoint_snapshot(endpoint) for endpoint in api_endpoints
    )

    if halt_reason:
        lowered = halt_reason.lower()
        blocker_type = "blocked"
        if "captcha" in lowered:
            blocker_type = "captcha"
        elif "mfa" in lowered:
            blocker_type = "mfa"
        blockers.append({"type": blocker_type, "page_url": halt_url, "message": halt_reason})

    session_type = "cookie"
    if any(
        header.lower() == "authorization"
        for endpoint in api_endpoints
        for header in (endpoint.request_headers or {})
    ):
        session_type = "bearer" if not cookie_names else "mixed"

    return {
        "persona_id": persona_id,
        "authenticated": authenticated,
        "login_detected": login_detected,
        "session_type": session_type,
        "protected_page_ids": protected_page_ids,
        "protected_api_endpoint_ids": protected_api_endpoint_ids,
        "cookie_names": sorted(cookie_names),
        "storage_keys": [],
        "blockers": blockers,
        "halt_reason": halt_reason,
        "halt_url": halt_url,
    }
