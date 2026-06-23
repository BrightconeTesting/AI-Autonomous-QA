"""Capture interactive elements and forms from a page or CIC scope."""

from __future__ import annotations

from aqa_discovery.extractors import extract_elements
from aqa_discovery.forms import extract_forms, link_elements_to_forms
from aqa_discovery.types import ElementSnapshot, FormSnapshot


def capture_interactive_data(
    page,
    scope=None,
    *,
    page_url: str | None = None,
    allowed_domains: list[str] | None = None,
) -> tuple[list[ElementSnapshot], list[FormSnapshot]]:
    """Extract enriched elements and linked forms from the current DOM scope."""
    elements = extract_elements(
        page,
        scope,
        page_url=page_url,
        allowed_domains=allowed_domains,
    )
    forms = extract_forms(page, scope)
    link_elements_to_forms(elements, forms)
    return elements, forms
