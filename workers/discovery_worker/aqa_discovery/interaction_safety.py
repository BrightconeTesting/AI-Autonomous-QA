"""Element-level interaction safety (CIC Phase 1)."""

from __future__ import annotations

import fnmatch
import re

from aqa_discovery.safety import _DANGEROUS_LINK_TEXT, is_safety_excluded_url
from aqa_discovery.types import ElementSnapshot

_SUBMIT_INPUT_TYPES = frozenset({"submit", "file", "image"})
_EXTERNAL_TARGET = re.compile(r"^_blank$", re.IGNORECASE)
_CHECKOUT_MARKERS = re.compile(
    r"\b(checkout|purchase|pay\s*now|confirm\s+order|place\s+order|buy\s+now)\b",
    re.IGNORECASE,
)

_SAFE_FILL_BY_TYPE: dict[str, str] = {
    "email": "test@example.com",
    "tel": "5550100",
    "number": "1",
    "url": "https://example.com",
    "search": "test",
    "date": "2026-01-01",
    "time": "09:00",
}
_DEFAULT_FILL = "Test value"


def canned_fill_value(attrs: dict) -> str:
    input_type = (attrs.get("type") or "text").lower()
    return _SAFE_FILL_BY_TYPE.get(input_type, _DEFAULT_FILL)


def build_interaction_key(element: ElementSnapshot) -> str:
    """Stable key for deduplicating interactions across states."""
    parts = [
        element.role or "",
        element.semantic_selector or "",
        element.xpath_fallback or "",
        (element.text_content or "")[:80],
        element.tag_name,
    ]
    return "|".join(parts)


def is_safe_to_interact(
    element: ElementSnapshot,
    *,
    page_url: str,
    blocked_patterns: list[str] | None = None,
    allow_form_submit: bool = False,
    allow_form_fill: bool | None = None,
) -> tuple[bool, str | None]:
    """Return (safe, skip_reason)."""
    form_fill = allow_form_fill if allow_form_fill is not None else allow_form_submit
    if not element.is_visible:
        return False, "not_visible"

    text = (element.text_content or "").strip()
    attrs = element.attributes or {}
    role = (element.role or "").lower()
    tag = element.tag_name.lower()
    input_type = (attrs.get("type") or "").lower()
    href = attrs.get("href") or ""

    if text and _DANGEROUS_LINK_TEXT.search(text):
        return False, "dangerous_text"

    for pattern in blocked_patterns or []:
        haystack = f"{text} {element.semantic_selector or ''} {element.xpath_fallback or ''}"
        if fnmatch.fnmatch(haystack.lower(), pattern.lower()):
            return False, "blocked_pattern"

    if tag == "input" and input_type in _SUBMIT_INPUT_TYPES:
        return False, "submit_or_file_input"

    if tag == "input" and input_type == "file":
        return False, "file_input"

    if not allow_form_submit and tag == "button" and attrs.get("type", "").lower() == "submit":
        return False, "form_submit"

    if href and is_safety_excluded_url(href):
        return False, "dangerous_href"

    if attrs.get("target") and _EXTERNAL_TARGET.match(str(attrs.get("target"))):
        return False, "external_target"

    if text and _CHECKOUT_MARKERS.search(text):
        return False, "checkout_action"

    if role == "link" and href and href.startswith("http") and page_url not in href:
        return False, "off_page_link"

    if tag == "select":
        return True, None

    if input_type in {"date", "datetime-local", "month"}:
        return True, None

    if role == "combobox" or attrs.get("aria-haspopup", "").lower() in {"listbox", "true"}:
        return True, None

    if role == "option":
        return True, None

    if role == "checkbox":
        return True, None

    if role in {"textbox"} or tag in {"input", "textarea"}:
        if not form_fill:
            return False, "form_fill_disabled"
        if input_type == "password":
            return False, "password_field"
        if input_type in {"file", "hidden", "submit"}:
            return False, "unsafe_input_type"
        return True, None

    return True, None
