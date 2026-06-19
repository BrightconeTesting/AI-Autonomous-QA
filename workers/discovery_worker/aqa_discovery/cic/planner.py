"""Interaction candidate planning (CIC Phase 1–3)."""

from __future__ import annotations

import re

from aqa_discovery.interaction_safety import build_interaction_key, canned_fill_value, is_safe_to_interact
from aqa_discovery.types import ElementSnapshot, InteractionAction

_WIZARD_BUTTON_TEXT = re.compile(r"^(next|continue|back|previous)$", re.IGNORECASE)
_PAGINATION_TEXT = re.compile(r"^(next|prev|previous|›|»|‹|«|next page|prev page)$", re.IGNORECASE)
_ROW_ACTION_TEXT = re.compile(r"^(view|edit|open|details)(\s+row)?(\s+\d+)?$", re.IGNORECASE)


def _is_hash_route_link(element: ElementSnapshot) -> bool:
    href = (element.attributes or {}).get("href") or ""
    return href.startswith("#/") or href.startswith("#!/")


def _is_modal_trigger(element: ElementSnapshot) -> bool:
    attrs = element.attributes or {}
    role = (element.role or "").lower()
    tag = element.tag_name.lower()
    if attrs.get("aria-haspopup", "").lower() == "dialog":
        return True
    if attrs.get("aria-controls") and role == "button" and tag == "button":
        return True
    if attrs.get("data-modal") is not None:
        return True
    return False


def _is_wizard_button(element: ElementSnapshot) -> bool:
    attrs = element.attributes or {}
    role = (element.role or "").lower()
    tag = element.tag_name.lower()
    if role not in {"button"} and tag not in {"button"}:
        return False
    if attrs.get("type", "").lower() == "submit":
        return False
    text = (element.text_content or "").strip()
    return bool(text and _WIZARD_BUTTON_TEXT.match(text))


def _is_native_select(element: ElementSnapshot) -> bool:
    return element.tag_name.lower() == "select"


def _is_custom_combobox(element: ElementSnapshot) -> bool:
    role = (element.role or "").lower()
    attrs = element.attributes or {}
    popup = (attrs.get("aria-haspopup") or "").lower()
    return role == "combobox" or popup in {"listbox", "true"} or attrs.get("role") == "combobox"


def _is_fillable_textbox(element: ElementSnapshot, *, safe_form_fill: bool) -> bool:
    if not safe_form_fill:
        return False
    role = (element.role or "").lower()
    tag = element.tag_name.lower()
    input_type = (element.attributes or {}).get("type", "text").lower()
    if input_type in {"password", "file", "hidden", "submit"}:
        return False
    return role == "textbox" or tag in {"input", "textarea"}


def _is_hover_menu_trigger(element: ElementSnapshot) -> bool:
    attrs = element.attributes or {}
    popup = (attrs.get("aria-haspopup") or "").lower()
    role = (element.role or "").lower()
    tag = element.tag_name.lower()
    return popup == "menu" and role in {"button", "menuitem"} and tag in {"button", "a"}


def _is_table_pagination(element: ElementSnapshot) -> bool:
    text = (element.text_content or "").strip()
    attrs = element.attributes or {}
    aria = (attrs.get("aria-label") or "").lower()
    if text and _PAGINATION_TEXT.match(text):
        return True
    return "next page" in aria or aria in {"next", "previous", "prev"}


def _is_table_row_action(element: ElementSnapshot) -> bool:
    role = (element.role or "").lower()
    text = (element.text_content or "").strip()
    attrs = element.attributes or {}
    if attrs.get("data-row") or attrs.get("data-row-index"):
        return True
    if role == "gridcell" and element.tag_name.lower() in {"button", "a"}:
        return True
    if text and _ROW_ACTION_TEXT.match(text):
        return True
    return bool(text and text.lower().startswith("view row"))


def _is_date_picker_trigger(element: ElementSnapshot) -> bool:
    attrs = element.attributes or {}
    tag = element.tag_name.lower()
    input_type = (attrs.get("type") or "").lower()
    if input_type in {"date", "datetime-local", "month"}:
        return True
    placeholder = (attrs.get("placeholder") or "").lower()
    aria = (attrs.get("aria-label") or "").lower()
    if "date" in placeholder or "mm/" in placeholder:
        return True
    if "date" in aria and tag in {"input", "button"}:
        return True
    if attrs.get("aria-haspopup") in {"dialog", "true"} and "date" in aria:
        return True
    return False


def _action_type_for(element: ElementSnapshot, *, safe_form_fill: bool, rich_interactions: bool) -> str | None:
    if _is_native_select(element) and rich_interactions:
        return "select"
    if _is_hover_menu_trigger(element) and rich_interactions:
        return "hover"
    if _is_fillable_textbox(element, safe_form_fill=safe_form_fill):
        return "fill"
    return "click"


def _priority(
    element: ElementSnapshot,
    *,
    in_page_only: bool,
    rich_interactions: bool,
    enable_tables: bool,
    enable_date_pickers: bool,
    safe_form_fill: bool,
) -> int | None:
    role = (element.role or "").lower()
    attrs = element.attributes or {}
    tag = element.tag_name.lower()

    if role == "tab":
        return 1
    if _is_modal_trigger(element):
        return 2
    if attrs.get("aria-expanded") == "false":
        return 2
    if tag == "summary":
        return 2
    if rich_interactions and _is_native_select(element):
        return 3
    if rich_interactions and _is_custom_combobox(element):
        return 3
    if rich_interactions and role == "checkbox":
        return 3
    if _is_hash_route_link(element):
        return 3
    if _is_wizard_button(element):
        return 3
    if rich_interactions and enable_date_pickers and _is_date_picker_trigger(element):
        return 3
    if rich_interactions and enable_tables and _is_table_pagination(element):
        return 4
    if rich_interactions and enable_tables and _is_table_row_action(element):
        return 4
    if rich_interactions and role == "option":
        return 4
    if rich_interactions and _is_hover_menu_trigger(element):
        return 4
    if in_page_only:
        if rich_interactions and _is_fillable_textbox(element, safe_form_fill=safe_form_fill):
            return 5
        return None
    if role == "menuitem":
        return 5
    if role in {"button"} and tag in {"button", "summary"}:
        return 6
    if role == "button":
        return 6
    if not in_page_only and role == "link" and tag == "a":
        return 6
    if rich_interactions and _is_fillable_textbox(element, safe_form_fill=safe_form_fill):
        return 6
    return None


def _is_navigation_element(element: ElementSnapshot) -> bool:
    if _is_hash_route_link(element):
        return False

    role = (element.role or "").lower()
    attrs = element.attributes or {}
    href = attrs.get("href") or ""
    if role == "link":
        return True
    tag = element.tag_name.lower()
    if tag == "a" and href and not _is_hover_menu_trigger(element):
        return True
    if role == "menuitem" and href.startswith("http"):
        return True
    return False


def plan_interactions(
    elements: list[ElementSnapshot],
    *,
    page_url: str,
    blocked_patterns: list[str] | None = None,
    already_interacted: set[str] | None = None,
    in_page_only: bool = True,
    max_candidates: int | None = None,
    safe_form_fill: bool = False,
    rich_interactions: bool = True,
    enable_tables: bool = True,
    enable_date_pickers: bool = True,
) -> list[InteractionAction]:
    """Build prioritized, safety-filtered interaction queue."""
    seen: set[str] = set()
    candidates: list[tuple[int, InteractionAction]] = []
    interacted = already_interacted or set()

    for element in elements:
        if not element.is_visible:
            continue
        if in_page_only and _is_navigation_element(element):
            continue

        key = build_interaction_key(element)
        if key in seen or key in interacted:
            continue
        seen.add(key)

        safe, _reason = is_safe_to_interact(
            element,
            page_url=page_url,
            blocked_patterns=blocked_patterns,
            allow_form_fill=safe_form_fill,
        )
        if not safe:
            continue

        action_type = _action_type_for(
            element,
            safe_form_fill=safe_form_fill,
            rich_interactions=rich_interactions,
        )
        if action_type is None:
            continue

        priority = _priority(
            element,
            in_page_only=in_page_only,
            rich_interactions=rich_interactions,
            enable_tables=enable_tables,
            enable_date_pickers=enable_date_pickers,
            safe_form_fill=safe_form_fill,
        )
        if priority is None:
            continue

        fill_value = None
        if action_type == "fill":
            fill_value = canned_fill_value(element.attributes or {})

        action = InteractionAction(
            action_type=action_type,
            interaction_key=key,
            semantic_selector=element.semantic_selector,
            xpath_fallback=element.xpath_fallback,
            role=element.role,
            text_content=element.text_content,
            value=fill_value,
        )
        candidates.append((priority, action))

    candidates.sort(key=lambda item: item[0])
    actions = [action for _, action in candidates]
    if max_candidates is not None:
        return actions[:max_candidates]
    return actions
