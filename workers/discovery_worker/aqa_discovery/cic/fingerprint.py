"""State fingerprinting for CIC deduplication."""

from __future__ import annotations

import hashlib
import json

from aqa_discovery.types import ElementSnapshot


def _element_signature(element: ElementSnapshot) -> str:
    attrs = element.attributes or {}
    selected = attrs.get("aria-selected") or attrs.get("aria-expanded") or ""
    return "|".join(
        [
            element.role or "",
            (element.text_content or "")[:60],
            element.tag_name,
            element.semantic_selector or element.xpath_fallback or "",
            str(selected),
        ]
    )


def _active_tab_signatures(elements: list[ElementSnapshot]) -> list[str]:
    """Capture selected tab / expanded panel markers for fingerprinting."""
    markers: list[str] = []
    for element in elements:
        if not element.is_visible:
            continue
        attrs = element.attributes or {}
        role = (element.role or "").lower()
        if role == "tab" and str(attrs.get("aria-selected", "")).lower() == "true":
            markers.append(f"tab:{(element.text_content or '')[:40]}")
        if str(attrs.get("aria-expanded", "")).lower() == "true":
            label = (element.text_content or attrs.get("aria-label") or element.semantic_selector or "")[:40]
            markers.append(f"expanded:{label}")
    return sorted(markers)


def compute_state_fingerprint(
    *,
    url: str,
    title: str,
    elements: list[ElementSnapshot],
    dialog_titles: list[str] | None = None,
) -> str:
    """Hash visible interactive signatures — not raw HTML."""
    visible = [e for e in elements if e.is_visible]
    signatures = sorted(_element_signature(e) for e in visible)
    active_tabs = _active_tab_signatures(elements)
    payload = {
        "url": url.split("?")[0].rstrip("/"),
        "title": (title or "")[:120],
        "dialogs": sorted(dialog_titles or []),
        "active_tabs": active_tabs,
        "elements": signatures[:200],
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return digest[:16]


def state_key_from_fingerprint(fingerprint: str) -> str:
    return f"s_{fingerprint}"
