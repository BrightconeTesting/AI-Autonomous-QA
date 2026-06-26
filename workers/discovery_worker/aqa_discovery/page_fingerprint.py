"""Page content fingerprinting for incremental delta crawl (Phase H)."""

from __future__ import annotations

from aqa_discovery.cic.fingerprint import compute_state_fingerprint
from aqa_discovery.types import ElementSnapshot, PageSnapshot


def compute_page_content_fingerprint(
    *,
    url: str,
    title: str,
    elements: list[ElementSnapshot],
) -> str:
    """Hash baseline interactive signatures for a crawled page."""
    return compute_state_fingerprint(url=url, title=title, elements=elements)


def fingerprint_from_page_snapshot(snapshot: PageSnapshot) -> str:
    if snapshot.content_fingerprint:
        return snapshot.content_fingerprint
    return compute_page_content_fingerprint(
        url=snapshot.url,
        title=snapshot.title,
        elements=snapshot.elements,
    )


def build_page_fingerprint_index(pages: list[PageSnapshot]) -> dict[str, str]:
    """Map normalized page URL → content fingerprint."""
    index: dict[str, str] = {}
    for page in pages:
        key = page.url.split("?")[0].rstrip("/")
        index[key] = fingerprint_from_page_snapshot(page)
    return index


def merge_page_fingerprints(
    existing: dict[str, str] | None,
    updates: dict[str, str],
) -> dict[str, str]:
    merged = dict(existing or {})
    merged.update(updates)
    return merged
