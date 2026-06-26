"""Capture interactive elements and forms from a page or CIC scope."""

from __future__ import annotations

from aqa_discovery.extractors import extract_elements
from aqa_discovery.forms import extract_forms, extract_virtual_forms, link_elements_to_forms, merge_forms
from aqa_discovery.types import ElementSnapshot, FormSnapshot


def capture_interactive_data(
    page,
    scope=None,
    *,
    page_url: str | None = None,
    allowed_domains: list[str] | None = None,
    pierce_shadow_dom: bool = True,
    include_virtual_forms: bool = False,
) -> tuple[list[ElementSnapshot], list[FormSnapshot]]:
    """Extract enriched elements and linked forms from the current DOM scope."""
    elements = extract_elements(
        page,
        scope,
        page_url=page_url,
        allowed_domains=allowed_domains,
        pierce_shadow_dom=pierce_shadow_dom,
    )
    native_forms = extract_forms(page, scope)
    if include_virtual_forms:
        virtual_forms = extract_virtual_forms(page, scope)
        forms = merge_forms(native_forms, virtual_forms)
    else:
        forms = native_forms
    link_elements_to_forms(elements, forms)
    return elements, forms
