"""Testability, button intent, and HTML5 constraint enrichment at crawl time."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

PII_KEYWORDS = (
    "password",
    "ssn",
    "social security",
    "credit card",
    "card number",
    "cvv",
)

DELETE_KEYWORDS = ("delete", "remove", "destroy", "trash")
CANCEL_KEYWORDS = ("cancel", "close", "dismiss", "back")
SUBMIT_KEYWORDS = ("save", "submit", "create", "add", "update", "confirm", "apply", "send")
FILTER_KEYWORDS = ("filter", "search", "sort", "refine")
TOGGLE_KEYWORDS = ("toggle", "expand", "collapse", "show", "hide", "more", "less")


def _clamp_score(value: float) -> int:
    return max(0, min(100, int(round(value))))


def classify_element_kind(*, tag_name: str, role: str | None, attributes: dict[str, Any] | None = None) -> str:
    tag = tag_name.lower()
    role_val = (role or "").lower()
    attrs = attributes or {}
    input_type = str(attrs.get("type") or "").lower()

    if tag == "form":
        return "form"
    if tag == "a" or role_val == "link":
        return "link"
    if tag == "select" or role_val == "combobox":
        return "select"
    if tag == "textarea" or role_val == "textbox":
        return "input"
    if tag == "button" or role_val == "button":
        return "button"
    if tag == "input":
        if input_type in {"checkbox"} or role_val == "checkbox":
            return "checkbox"
        if input_type in {"radio"} or role_val == "radio":
            return "radio"
        if input_type in {"submit", "button", "reset"}:
            return "button"
        return "input"
    if role_val in {"tab", "menuitem", "option", "gridcell", "row"}:
        return role_val
    return tag or "unknown"


def classify_button_intent(
    *,
    tag_name: str,
    role: str | None,
    text_content: str | None,
    attributes: dict[str, Any] | None = None,
) -> str:
    tag = tag_name.lower()
    role_val = (role or "").lower()
    attrs = attributes or {}
    input_type = str(attrs.get("type") or "").lower()
    text = (text_content or "").lower().strip()
    aria = str(attrs.get("aria-label") or "").lower()

    is_button = tag == "button" or role_val == "button" or (tag == "input" and input_type in {"submit", "button", "reset"})
    if not is_button:
        return "unknown"

    blob = f"{text} {aria}"
    if any(kw in blob for kw in DELETE_KEYWORDS):
        return "delete"
    if input_type == "reset" or any(kw in blob for kw in CANCEL_KEYWORDS):
        return "cancel"
    if input_type == "submit" or any(kw in blob for kw in SUBMIT_KEYWORDS):
        return "submit"
    if any(kw in blob for kw in FILTER_KEYWORDS):
        return "filter"
    if str(attrs.get("aria-expanded") or "") in {"true", "false"} or any(kw in blob for kw in TOGGLE_KEYWORDS):
        return "toggle"
    if attrs.get("href"):
        return "navigate"
    return "unknown"


def extract_html5_constraints(attributes: dict[str, Any] | None) -> dict[str, Any]:
    attrs = attributes or {}
    constraints: dict[str, Any] = {}
    for key in ("required", "pattern", "min", "max", "minlength", "maxlength", "step", "type"):
        value = attrs.get(key)
        if value is None or value == "":
            continue
        if key == "required":
            constraints[key] = value is True or str(value).lower() in {"true", "required", ""}
        else:
            constraints[key] = value
    return constraints


def classify_testability_tier(*, semantic_selector: str | None, xpath_fallback: str | None) -> str:
    selector = (semantic_selector or "").strip()
    xpath = (xpath_fallback or "").strip()
    if selector.startswith("getByRole(") or selector.startswith("getByLabel(") or selector.startswith("getByTestId("):
        return "action"
    if selector.startswith("getByPlaceholder(") or selector.startswith("getByText("):
        return "action"
    if selector.startswith("locator("):
        return "assert_only"
    if xpath and not selector:
        return "xpath_only"
    if not selector and not xpath:
        return "panel"
    return "assert_only"


def score_element_testability(element: dict[str, Any]) -> int:
    """0–100 testability from semantic locator quality."""
    selector = str(element.get("semantic_selector") or "").strip()
    xpath = str(element.get("xpath_fallback") or "").strip()
    role = str(element.get("role") or "").lower()
    text = str(element.get("text_content") or "").lower()

    if not selector and not xpath and not role:
        return 20

    score = 40.0
    if selector.startswith("getByRole("):
        score += 35
    elif selector.startswith("getByLabel(") or selector.startswith("getByTestId("):
        score += 30
    elif selector.startswith("getByPlaceholder(") or selector.startswith("getByText("):
        score += 20
    elif selector.startswith("#") or selector.startswith("."):
        score -= 25
    elif selector.startswith("//") or xpath:
        score -= 20

    if re.search(r"#\d{3,}|id=['\"][^'\"]*\d{5,}", selector + xpath, re.I):
        score -= 15

    if any(kw in text for kw in PII_KEYWORDS):
        score -= 5

    if role in {"button", "link", "textbox", "combobox", "checkbox"}:
        score += 5

    tier = classify_testability_tier(semantic_selector=selector or None, xpath_fallback=xpath or None)
    if tier == "xpath_only":
        score -= 10
    elif tier == "panel":
        score -= 15

    return _clamp_score(score)


def classify_link_scope(
    *,
    href: str | None,
    page_url: str | None,
    allowed_domains: list[str] | None = None,
) -> str | None:
    if not href:
        return None
    href = href.strip()
    if href.startswith("#") or href.lower().startswith("javascript:"):
        return "internal"
    if href.startswith("/"):
        return "internal"

    parsed = urlparse(href)
    if not parsed.scheme and not parsed.netloc:
        return "internal"
    if not parsed.hostname:
        return "internal"

    host = parsed.hostname.lower()
    page_host = urlparse(page_url or "").hostname
    if page_host and host == page_host.lower():
        return "internal"

    allowed = {domain.lower() for domain in (allowed_domains or [])}
    if allowed and host in allowed:
        return "internal"
    return "external"


def enrich_element_attributes(
    *,
    tag_name: str,
    role: str | None,
    text_content: str | None,
    semantic_selector: str | None,
    xpath_fallback: str | None,
    attributes: dict[str, Any],
    page_url: str | None = None,
    allowed_domains: list[str] | None = None,
) -> dict[str, Any]:
    """Return merged element attributes with testability enrichment."""
    enriched = dict(attributes)
    element_kind = classify_element_kind(tag_name=tag_name, role=role, attributes=enriched)
    enriched["element_kind"] = element_kind

    tier = classify_testability_tier(semantic_selector=semantic_selector, xpath_fallback=xpath_fallback)
    enriched["testability_tier"] = tier

    element_dict = {
        "semantic_selector": semantic_selector,
        "xpath_fallback": xpath_fallback,
        "role": role,
        "text_content": text_content,
    }
    enriched["testability_score"] = score_element_testability(element_dict)

    html5 = extract_html5_constraints(enriched)
    if html5:
        enriched["html5"] = html5

    if element_kind in {"button", "input"} or (role or "").lower() == "button":
        intent = classify_button_intent(
            tag_name=tag_name,
            role=role,
            text_content=text_content,
            attributes=enriched,
        )
        if intent != "unknown":
            enriched["button_intent"] = intent

    href = enriched.get("href")
    link_scope = classify_link_scope(href=str(href) if href else None, page_url=page_url, allowed_domains=allowed_domains)
    if link_scope:
        enriched["link_scope"] = link_scope
        if link_scope == "external" and href:
            external_host = urlparse(str(href)).hostname
            if external_host:
                enriched["external_host"] = external_host

    return enriched
