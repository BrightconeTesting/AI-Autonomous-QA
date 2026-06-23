"""SPA route catalog assembly for AppMap (DISCOVERY-AGENT-VISION-SPEC §8.8)."""

from __future__ import annotations

import re
import uuid
from typing import Any
from urllib.parse import urlparse

from aqa_shared.discovery.persona_merge import _module_key


def _is_hash_spa_url(url: str) -> bool:
    fragment = urlparse(url or "").fragment
    if not fragment:
        return False
    stripped = fragment.lstrip("!")
    return bool(stripped) and (fragment.startswith("/") or fragment.startswith("!/") or stripped.startswith("/"))


def _route_path_from_url(url: str) -> str:
    parsed = urlparse(url or "")
    if parsed.fragment:
        fragment = parsed.fragment.lstrip("!")
        if fragment.startswith("/"):
            return fragment.split("?")[0] or "/"
        if fragment:
            return f"/{fragment.split('?')[0]}"
    path = parsed.path or "/"
    return path.split("?")[0] or "/"


def infer_path_pattern(url: str) -> str:
    """Heuristic path pattern — numeric/uuid segments become :id."""
    route_path = _route_path_from_url(url)
    parts: list[str] = []
    uuid_re = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        re.I,
    )
    for part in route_path.split("/"):
        if not part:
            continue
        if part.isdigit() or uuid_re.match(part):
            parts.append(":id")
        else:
            parts.append(part.lower())
    return "/" + "/".join(parts) if parts else "/"


def _page_id_for_url(url: str, pages: list[dict[str, Any]]) -> str | None:
    normalized = url.split("#")[0].rstrip("/")
    for page in pages:
        page_url = str(page.get("url") or "")
        if page_url == url or page_url.split("#")[0].rstrip("/") == normalized:
            return str(page.get("page_id") or "") or None
    for page in pages:
        page_url = str(page.get("url") or "")
        if normalized and normalized in page_url:
            return str(page.get("page_id") or "") or None
    return None


def _module_id_for_page(page_id: str | None, modules: list[dict[str, Any]], url: str) -> str | None:
    if page_id:
        for module in modules:
            if page_id in [str(item) for item in (module.get("pages") or [])]:
                return str(module.get("module_id") or "") or None
    key = _module_key(url)
    for module in modules:
        if str(module.get("module_id") or "").lower() == key:
            return str(module.get("module_id") or "") or None
    return key or None


def _confidence_for_method(method: str) -> float:
    if method in {"pushstate_listener", "replace_state_listener", "replacestate_listener"}:
        return 0.85
    if method == "popstate_listener":
        return 0.8
    if method == "hash_route":
        return 0.75
    if method == "cic_interaction":
        return 0.7
    if method == "link_extraction":
        return 0.65
    return 0.6


def build_spa_routes(
    *,
    pages: list[dict[str, Any]],
    modules: list[dict[str, Any]],
    discoveries: list[dict[str, Any]] | None = None,
    transitions: list[dict[str, Any]] | None = None,
    crawl_events: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build AppMap spa_routes[] from crawl events, hash URLs, and CIC discoveries."""
    routes: list[dict[str, Any]] = []
    by_pattern: dict[str, dict[str, Any]] = {}

    def _upsert(
        *,
        url: str,
        discovery_method: str,
        page_id: str | None,
        module_id: str | None,
        confidence: float | None = None,
    ) -> None:
        if not url:
            return
        pattern = infer_path_pattern(url)
        entry = by_pattern.get(pattern)
        if entry is None:
            entry = {
                "route_id": str(uuid.uuid4()),
                "path_pattern": pattern,
                "url_examples": [],
                "discovery_methods": [],
                "page_id": page_id,
                "module_id": module_id,
                "confidence": confidence or _confidence_for_method(discovery_method),
            }
            by_pattern[pattern] = entry
        examples = entry["url_examples"]
        if url not in examples:
            examples.append(url)
        methods = entry["discovery_methods"]
        if discovery_method not in methods:
            methods.append(discovery_method)
        if page_id and not entry.get("page_id"):
            entry["page_id"] = page_id
        if module_id and not entry.get("module_id"):
            entry["module_id"] = module_id
        entry["confidence"] = max(float(entry.get("confidence") or 0), confidence or _confidence_for_method(discovery_method))

    for event in crawl_events or []:
        to_url = str(event.get("to_url") or event.get("url") or "").strip()
        if not to_url:
            continue
        source = str(event.get("source_page_url") or "")
        page_id = _page_id_for_url(source or to_url, pages)
        _upsert(
            url=to_url,
            discovery_method=str(event.get("discovery_method") or "pushstate_listener"),
            page_id=page_id,
            module_id=_module_id_for_page(page_id, modules, to_url),
        )

    for page in pages:
        url = str(page.get("url") or "")
        if _is_hash_spa_url(url):
            page_id = str(page.get("page_id") or "") or None
            _upsert(
                url=url,
                discovery_method="hash_route",
                page_id=page_id,
                module_id=_module_id_for_page(page_id, modules, url),
            )

    for discovery in discoveries or []:
        url = str(discovery.get("url") or "")
        if not _is_hash_spa_url(url):
            continue
        source_page_id = str(discovery.get("source_page_id") or "") or None
        _upsert(
            url=url,
            discovery_method="cic_interaction"
            if str(discovery.get("discovered_via") or "") == "interaction"
            else "link_extraction",
            page_id=source_page_id or _page_id_for_url(url, pages),
            module_id=_module_id_for_page(source_page_id, modules, url),
        )

    for transition in transitions or []:
        action = transition.get("action") or {}
        if str(action.get("action_type") or "") not in {"click", "select"}:
            continue
        # URL-changing interactions are captured via discoveries/events; transitions add confidence only.
        continue

    for entry in by_pattern.values():
        methods = entry.pop("discovery_methods", [])
        primary_method = methods[0] if methods else "pushstate_listener"
        routes.append(
            {
                "route_id": entry["route_id"],
                "path_pattern": entry["path_pattern"],
                "url_examples": entry["url_examples"][:5],
                "discovery_method": primary_method,
                "discovery_methods": methods,
                "page_id": entry.get("page_id"),
                "module_id": entry.get("module_id"),
                "confidence": round(float(entry.get("confidence") or 0.6), 2),
            }
        )

    routes.sort(key=lambda item: (str(item.get("path_pattern") or ""), str(item.get("discovery_method") or "")))
    return routes
