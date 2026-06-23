"""Multi-persona visibility merge (DISCOVERY-AGENT-VISION-SPEC §19.4)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


def _module_key(url: str) -> str:
    path = urlparse(url or "").path
    parts = [part for part in path.split("/") if part]
    if "index.php" in parts:
        index = parts.index("index.php")
        if index + 1 < len(parts):
            return parts[index + 1].lower()
    if len(parts) >= 2:
        return parts[-2].lower()
    if parts:
        return parts[-1].lower()
    fragment = urlparse(url or "").fragment
    if fragment:
        return fragment.strip("/").split("/")[0].lower() or "root"
    return "root"


def _module_ids_for_page(page: dict[str, Any], modules: list[dict[str, Any]]) -> list[str]:
    page_id = str(page.get("page_id") or "")
    matched = [
        str(module.get("module_id") or "")
        for module in modules
        if page_id in [str(item) for item in (module.get("pages") or [])]
    ]
    if matched:
        return matched
    return [_module_key(str(page.get("url") or ""))]


def build_visibility_matrix(
    *,
    modules: list[dict[str, Any]],
    persona_visibility: dict[str, Any],
) -> dict[str, dict[str, list[str]]]:
    """Compute visible and exclusive module ids per persona."""
    page_personas: dict[str, list[str]] = persona_visibility.get("page_personas") or {}
    pages_by_url = {str(page.get("url") or ""): page for page in (persona_visibility.get("pages") or [])}

    persona_modules: dict[str, set[str]] = {}
    module_personas: dict[str, set[str]] = {}

    for url, persona_ids in page_personas.items():
        page = pages_by_url.get(url) or {"url": url}
        module_ids = _module_ids_for_page(page, modules)
        for persona_id in persona_ids:
            persona_modules.setdefault(str(persona_id), set()).update(module_ids)
            for module_id in module_ids:
                module_personas.setdefault(module_id, set()).add(str(persona_id))

    matrix: dict[str, dict[str, list[str]]] = {}
    for persona in persona_visibility.get("personas") or []:
        persona_id = str(persona.get("persona_id") or "")
        if not persona_id:
            continue
        visible = sorted(persona_modules.get(persona_id, set()))
        exclusive = sorted(
            module_id
            for module_id in visible
            if len(module_personas.get(module_id, set())) == 1
            and persona_id in module_personas.get(module_id, set())
        )
        matrix[persona_id] = {
            "visible_module_ids": visible,
            "exclusive_module_ids": exclusive,
        }
    return matrix


def build_persona_visibility_artifact(
    *,
    persona_results: list[dict[str, Any]],
) -> dict[str, Any]:
    page_personas: dict[str, list[str]] = {}
    for result in persona_results:
        persona_id = str(result.get("persona_id") or "")
        for url in result.get("page_urls") or []:
            bucket = page_personas.setdefault(str(url), [])
            if persona_id and persona_id not in bucket:
                bucket.append(persona_id)
    return {
        "personas": persona_results,
        "page_personas": page_personas,
    }
