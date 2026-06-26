"""Interactive element extraction and locator generation (SPEC §12, Day 19)."""

from __future__ import annotations

import json
from typing import Any

from aqa_discovery.interaction_safety import build_interaction_key
from aqa_discovery.types import ElementSnapshot
from aqa_shared.testability.enrichment import enrich_element_attributes

_INTERACTIVE_SELECTOR = (
    "a[href], button, input:not([type='hidden']), select, textarea, "
    "[role='button'], [role='link'], [role='checkbox'], [role='radio'], "
    "[role='textbox'], [role='combobox'], [role='menuitem'], [role='tab'], "
    "[role='option'], [role='listbox'], [role='gridcell'], [role='row'], "
    "table button, table a[href], summary"
)

_SHADOW_PIERCE_EXTRACT_JS = """
(selector) => {
  const seen = new Set();
  const collected = [];

  function resolveFieldLabel(element) {
    if (element.labels && element.labels.length > 0) {
      return (element.labels[0].innerText || element.labels[0].textContent || '').trim().slice(0, 200);
    }
    const id = element.getAttribute('id');
    if (id) {
      const labelEl = element.ownerDocument.querySelector(`label[for="${CSS.escape(id)}"]`);
      if (labelEl) return (labelEl.innerText || labelEl.textContent || '').trim().slice(0, 200);
    }
    const labelledBy = element.getAttribute('aria-labelledby');
    if (labelledBy) {
      const text = labelledBy.split(/\\s+/)
        .map((part) => element.ownerDocument.getElementById(part))
        .filter(Boolean)
        .map((el) => (el.innerText || el.textContent || '').trim())
        .filter(Boolean)
        .join(' ');
      if (text) return text.slice(0, 200);
    }
    const parentLabel = element.closest('label');
    if (parentLabel) {
      const clone = parentLabel.cloneNode(true);
      clone.querySelectorAll('input,select,textarea').forEach((node) => node.remove());
      const wrapped = (clone.innerText || clone.textContent || '').trim().replace(/\\s+/g, ' ');
      if (wrapped) return wrapped.slice(0, 200);
    }
    let node = element;
    for (let depth = 0; depth < 5; depth++) {
      let prev = node.previousElementSibling;
      while (prev) {
        const text = (prev.innerText || prev.textContent || '').trim().replace(/\\s+/g, ' ');
        if (text && text.length >= 2 && text.length <= 120) return text.slice(0, 200);
        prev = prev.previousElementSibling;
      }
      if (!node.parentElement) break;
      node = node.parentElement;
      const direct = node.querySelector(':scope > label, :scope > span, :scope > p');
      if (direct && direct !== element && !direct.contains(element)) {
        const text = (direct.innerText || direct.textContent || '').trim().replace(/\\s+/g, ' ');
        if (text && text.length >= 2 && text.length <= 120) return text.slice(0, 200);
      }
    }
    return '';
  }

  function walk(root) {
    root.querySelectorAll(selector).forEach(element => {
      if (seen.has(element)) return;
      seen.add(element);
      collected.push(element);
    });
    root.querySelectorAll('*').forEach(node => {
      if (node.shadowRoot) walk(node.shadowRoot);
    });
  }

  function mapElement(element) {
    const tag = element.tagName.toLowerCase();
    const type = (element.getAttribute('type') || '').toLowerCase();
    const roleAttr = element.getAttribute('role');
    const ariaLabel = element.getAttribute('aria-label') || '';
    const placeholder = element.getAttribute('placeholder') || '';
    const testId = element.getAttribute('data-testid') || element.getAttribute('data-test-id') || '';
    const id = element.getAttribute('id') || '';
    const text = (element.innerText || element.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 200);

    let role = roleAttr || '';
    if (!role) {
      if (tag === 'a') role = 'link';
      else if (tag === 'button') role = 'button';
      else if (tag === 'select') role = 'combobox';
      else if (tag === 'textarea') role = 'textbox';
      else if (tag === 'input') {
        if (type === 'checkbox') role = 'checkbox';
        else if (type === 'radio') role = 'radio';
        else if (type === 'submit' || type === 'button') role = 'button';
        else role = 'textbox';
      } else if (tag === 'summary') role = 'button';
    }

    let label = resolveFieldLabel(element);
    if (!label && element.labels && element.labels.length > 0) {
      label = (element.labels[0].innerText || element.labels[0].textContent || '').trim().slice(0, 200);
    } else if (!label && id) {
      const labelEl = element.ownerDocument.querySelector(`label[for="${CSS.escape(id)}"]`);
      if (labelEl) {
        label = (labelEl.innerText || labelEl.textContent || '').trim().slice(0, 200);
      }
    }

    const accessibleName = ariaLabel || label || text;

    function getXPath(el) {
      if (el.id) return `//*[@id="${el.id.replace(/"/g, '\\\\"')}"]`;
      const parts = [];
      while (el && el.nodeType === Node.ELEMENT_NODE) {
        let index = 1;
        let sibling = el.previousElementSibling;
        while (sibling) {
          if (sibling.tagName === el.tagName) index += 1;
          sibling = sibling.previousElementSibling;
        }
        parts.unshift(`${el.tagName.toLowerCase()}[${index}]`);
        el = el.parentElement;
      }
      return '/' + parts.join('/');
    }

    const attributes = {};
    for (const attr of ['id', 'name', 'type', 'href', 'value', 'class', 'aria-label', 'data-testid', 'aria-expanded', 'aria-haspopup', 'aria-controls', 'data-modal', 'required', 'pattern', 'min', 'max', 'minlength', 'maxlength', 'step']) {
      const value = element.getAttribute(attr);
      if (value !== null && value !== '') attributes[attr] = value.slice(0, 500);
    }
    if (element.required) attributes.required = 'true';
    if (placeholder) attributes.placeholder = placeholder.slice(0, 500);
    if (label) attributes.label = label.slice(0, 500);
    if (element.getRootNode() instanceof ShadowRoot) attributes.shadowRoot = 'true';

    const rect = element.getBoundingClientRect();
    const style = window.getComputedStyle(element);
    const visible = rect.width > 0 && rect.height > 0
      && style.visibility !== 'hidden' && style.display !== 'none' && parseFloat(style.opacity || '1') > 0;

    return {
      tag,
      role,
      text,
      label,
      placeholder,
      testId,
      accessibleName,
      xpath: getXPath(element),
      attributes,
      visible,
    };
  }

  walk(document);
  return collected.map(mapElement);
}
"""

_EXTRACT_ELEMENTS_JS = """
elements => {
  function resolveFieldLabel(element) {
    if (element.labels && element.labels.length > 0) {
      return (element.labels[0].innerText || element.labels[0].textContent || '').trim().slice(0, 200);
    }
    const id = element.getAttribute('id');
    if (id) {
      const labelEl = element.ownerDocument.querySelector(`label[for="${CSS.escape(id)}"]`);
      if (labelEl) return (labelEl.innerText || labelEl.textContent || '').trim().slice(0, 200);
    }
    const labelledBy = element.getAttribute('aria-labelledby');
    if (labelledBy) {
      const text = labelledBy.split(/\\s+/)
        .map((part) => element.ownerDocument.getElementById(part))
        .filter(Boolean)
        .map((el) => (el.innerText || el.textContent || '').trim())
        .filter(Boolean)
        .join(' ');
      if (text) return text.slice(0, 200);
    }
    const parentLabel = element.closest('label');
    if (parentLabel) {
      const clone = parentLabel.cloneNode(true);
      clone.querySelectorAll('input,select,textarea').forEach((node) => node.remove());
      const wrapped = (clone.innerText || clone.textContent || '').trim().replace(/\\s+/g, ' ');
      if (wrapped) return wrapped.slice(0, 200);
    }
    let node = element;
    for (let depth = 0; depth < 5; depth++) {
      let prev = node.previousElementSibling;
      while (prev) {
        const text = (prev.innerText || prev.textContent || '').trim().replace(/\\s+/g, ' ');
        if (text && text.length >= 2 && text.length <= 120) return text.slice(0, 200);
        prev = prev.previousElementSibling;
      }
      if (!node.parentElement) break;
      node = node.parentElement;
      const direct = node.querySelector(':scope > label, :scope > span, :scope > p');
      if (direct && direct !== element && !direct.contains(element)) {
        const text = (direct.innerText || direct.textContent || '').trim().replace(/\\s+/g, ' ');
        if (text && text.length >= 2 && text.length <= 120) return text.slice(0, 200);
      }
    }
    return '';
  }

  return elements.map(element => {
  const tag = element.tagName.toLowerCase();
  const type = (element.getAttribute('type') || '').toLowerCase();
  const roleAttr = element.getAttribute('role');
  const ariaLabel = element.getAttribute('aria-label') || '';
  const placeholder = element.getAttribute('placeholder') || '';
  const testId = element.getAttribute('data-testid') || element.getAttribute('data-test-id') || '';
  const id = element.getAttribute('id') || '';
  const text = (element.innerText || element.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 200);

  let role = roleAttr || '';
  if (!role) {
    if (tag === 'a') role = 'link';
    else if (tag === 'button') role = 'button';
    else if (tag === 'select') role = 'combobox';
    else if (tag === 'textarea') role = 'textbox';
    else if (tag === 'input') {
      if (type === 'checkbox') role = 'checkbox';
      else if (type === 'radio') role = 'radio';
      else if (type === 'submit' || type === 'button') role = 'button';
      else role = 'textbox';
    } else if (tag === 'summary') role = 'button';
  }

  let label = resolveFieldLabel(element);
  if (!label && element.labels && element.labels.length > 0) {
    label = (element.labels[0].innerText || element.labels[0].textContent || '').trim().slice(0, 200);
  } else if (!label && id) {
    const labelEl = element.ownerDocument.querySelector(`label[for="${CSS.escape(id)}"]`);
    if (labelEl) {
      label = (labelEl.innerText || labelEl.textContent || '').trim().slice(0, 200);
    }
  }

  const accessibleName = ariaLabel || label || text;

  function getXPath(el) {
    if (el.id) return `//*[@id="${el.id.replace(/"/g, '\\\\"')}"]`;
    const parts = [];
    while (el && el.nodeType === Node.ELEMENT_NODE) {
      let index = 1;
      let sibling = el.previousElementSibling;
      while (sibling) {
        if (sibling.tagName === el.tagName) index += 1;
        sibling = sibling.previousElementSibling;
      }
      parts.unshift(`${el.tagName.toLowerCase()}[${index}]`);
      el = el.parentElement;
    }
    return '/' + parts.join('/');
  }

  const attributes = {};
  for (const attr of ['id', 'name', 'type', 'href', 'value', 'class', 'aria-label', 'data-testid', 'aria-expanded', 'aria-haspopup', 'aria-controls', 'data-modal', 'required', 'pattern', 'min', 'max', 'minlength', 'maxlength', 'step']) {
    const value = element.getAttribute(attr);
    if (value !== null && value !== '') attributes[attr] = value.slice(0, 500);
  }
  if (element.required) attributes.required = 'true';
  if (placeholder) attributes.placeholder = placeholder.slice(0, 500);
  if (label) attributes.label = label.slice(0, 500);

  const rect = element.getBoundingClientRect();
  const style = window.getComputedStyle(element);
  const visible = rect.width > 0 && rect.height > 0
    && style.visibility !== 'hidden' && style.display !== 'none' && parseFloat(style.opacity || '1') > 0;

  return {
    tag,
    role,
    text,
    label,
    placeholder,
    testId,
    accessibleName,
    xpath: getXPath(element),
    attributes,
    visible,
  };
});
}
"""


def _escape_js_string(value: str) -> str:
    return json.dumps(value[:80])


def _build_css_selector(raw: dict[str, Any]) -> str | None:
    attrs = raw.get("attributes") or {}
    tag = raw.get("tag") or "*"
    element_id = attrs.get("id")
    name = attrs.get("name")
    test_id = attrs.get("data-testid") or raw.get("testId")

    if test_id:
        return f"[data-testid={json.dumps(test_id)}]"
    if element_id:
        return f"{tag}#{element_id}"
    if name:
        return f"{tag}[name={json.dumps(name)}]"
    input_type = attrs.get("type")
    if tag == "input" and input_type:
        return f"input[type={json.dumps(input_type)}]"
    href = attrs.get("href")
    if tag == "a" and href:
        return f"a[href={json.dumps(href[:200])}]"
    return None


def build_locators(raw: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return (semantic_selector, xpath_fallback) using SPEC §12 priority order."""
    role = (raw.get("role") or "").strip()
    accessible_name = (raw.get("accessibleName") or "").strip()
    label = (raw.get("label") or "").strip()
    placeholder = (raw.get("placeholder") or "").strip()
    text = (raw.get("text") or "").strip()
    test_id = (raw.get("testId") or "").strip()
    tag = (raw.get("tag") or "").strip()
    xpath = (raw.get("xpath") or "").strip() or None

    if label:
        return f"getByLabel({_escape_js_string(label)})", xpath

    if role and accessible_name:
        return f"getByRole({json.dumps(role)}, {{ name: {_escape_js_string(accessible_name)} }})", xpath

    if placeholder and tag in {"input", "textarea"}:
        return f"getByPlaceholder({_escape_js_string(placeholder)})", xpath

    if text and len(text) <= 80:
        return f"getByText({_escape_js_string(text)})", xpath

    if test_id:
        return f"getByTestId({json.dumps(test_id)})", xpath

    css = _build_css_selector(raw)
    if css:
        return f"locator('css={css}')", xpath

    return None, xpath


def extract_elements(
    page,
    scope=None,
    *,
    page_url: str | None = None,
    allowed_domains: list[str] | None = None,
    pierce_shadow_dom: bool = True,
) -> list[ElementSnapshot]:
    """Extract interactive elements from an open Playwright page or CIC scope."""
    target = scope if scope is not None else page
    if pierce_shadow_dom:
        raw_elements = page.evaluate(_SHADOW_PIERCE_EXTRACT_JS, _INTERACTIVE_SELECTOR)
    else:
        eval_fn = getattr(target, "eval_on_selector_all", None)
        if eval_fn is None:
            eval_fn = page.eval_on_selector_all
        raw_elements = eval_fn(
            _INTERACTIVE_SELECTOR,
            _EXTRACT_ELEMENTS_JS,
        )

    snapshots: list[ElementSnapshot] = []
    seen: set[str] = set()
    resolved_page_url = page_url or getattr(page, "url", None)

    for raw in raw_elements:
        semantic, xpath = build_locators(raw)
        tag = str(raw.get("tag") or "").lower()
        if tag in {"input", "textarea", "select"} and xpath:
            dedupe_key = xpath
        else:
            dedupe_key = semantic or xpath or tag
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        base_attrs = dict(raw.get("attributes") or {})
        if raw.get("label"):
            base_attrs.setdefault("label", str(raw.get("label"))[:500])
        if raw.get("placeholder"):
            base_attrs.setdefault("placeholder", str(raw.get("placeholder"))[:500])
        if raw.get("accessibleName"):
            base_attrs.setdefault("accessible_name", str(raw.get("accessibleName"))[:500])

        attributes = enrich_element_attributes(
            tag_name=str(raw.get("tag") or "unknown"),
            role=(raw.get("role") or None),
            text_content=(raw.get("text") or None),
            semantic_selector=semantic,
            xpath_fallback=xpath,
            attributes=base_attrs,
            page_url=resolved_page_url,
            allowed_domains=allowed_domains,
        )

        item = ElementSnapshot(
            tag_name=str(raw.get("tag") or "unknown")[:64],
            role=(raw.get("role") or None),
            text_content=(raw.get("text") or None),
            semantic_selector=semantic,
            xpath_fallback=xpath,
            attributes=attributes,
            is_visible=bool(raw.get("visible", True)),
        )
        item.interaction_key = build_interaction_key(item)
        snapshots.append(item)

    return snapshots


def diff_elements(before: list[ElementSnapshot], after: list[ElementSnapshot]) -> list[ElementSnapshot]:
    """Return elements in after that are not in before (by interaction_key)."""
    before_keys = {e.interaction_key or build_interaction_key(e) for e in before}
    new_elements: list[ElementSnapshot] = []
    for element in after:
        key = element.interaction_key or build_interaction_key(element)
        if key not in before_keys and element.is_visible:
            new_elements.append(element)
    return new_elements


def detect_dialog_titles(page) -> list[str]:
    """Return visible dialog titles for fingerprinting."""
    try:
        return page.eval_on_selector_all(
            "[role='dialog'], [aria-modal='true']",
            "els => els.map(e => (e.getAttribute('aria-label') || e.querySelector('h1,h2,h3')?.textContent || '').trim()).filter(Boolean)",
        )
    except Exception:
        return []


def save_page_screenshot(page, dest_path) -> int:
    """Capture a full-page screenshot; return file size in bytes."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(dest_path), full_page=True)
    return dest_path.stat().st_size
