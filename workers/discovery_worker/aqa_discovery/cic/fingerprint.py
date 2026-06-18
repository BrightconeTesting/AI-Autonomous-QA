"""State fingerprinting for CIC deduplication."""

from __future__ import annotations

import hashlib
import json

from aqa_discovery.types import ElementSnapshot


def _element_signature(element: ElementSnapshot) -> str:
    return "|".join(
        [
            element.role or "",
            (element.text_content or "")[:60],
            element.tag_name,
            element.semantic_selector or element.xpath_fallback or "",
        ]
    )


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
    payload = {
        "url": url.split("?")[0].rstrip("/"),
        "title": (title or "")[:120],
        "dialogs": sorted(dialog_titles or []),
        "elements": signatures[:200],
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return digest[:16]


def state_key_from_fingerprint(fingerprint: str) -> str:
    return f"s_{fingerprint}"
