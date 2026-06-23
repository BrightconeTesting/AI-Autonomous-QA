"""Form detection during crawl (DISCOVERY-AGENT-VISION-SPEC §8.2)."""

from __future__ import annotations

from typing import Any

from aqa_discovery.types import ElementSnapshot, FormSnapshot

_EXTRACT_FORMS_JS = """
() => {
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

  return Array.from(document.querySelectorAll('form')).map((form, index) => {
    const fields = Array.from(
      form.querySelectorAll("input:not([type='hidden']), select, textarea")
    );
    const legend = form.querySelector('legend');
    const legendText = legend ? (legend.innerText || legend.textContent || '').trim() : '';
    const id = form.getAttribute('id') || '';
    const name = form.getAttribute('name') || '';
    const action = form.getAttribute('action') || '';
    const method = (form.getAttribute('method') || 'get').toLowerCase();
    const formKey = id || name || (action ? `action:${action}` : `form-${index}`);

    return {
      form_key: formKey.slice(0, 200),
      name: (legendText || name || id || `Form ${index + 1}`).slice(0, 200),
      action: action.slice(0, 500),
      method,
      attributes: {
        id: id || undefined,
        name: name || undefined,
        enctype: form.getAttribute('enctype') || undefined,
        novalidate: form.hasAttribute('novalidate') || undefined,
      },
      field_xpaths: fields.map((field) => getXPath(field)),
    };
  });
}
"""


def extract_forms(page, scope=None) -> list[FormSnapshot]:
    """Extract `<form>` nodes and associated field xpaths from a Playwright page or CIC scope."""
    target = scope if scope is not None else page
    eval_fn = getattr(target, "evaluate", None)
    if eval_fn is None:
        eval_fn = page.evaluate

    raw_forms: list[dict[str, Any]] = eval_fn(_EXTRACT_FORMS_JS)
    forms: list[FormSnapshot] = []
    seen_keys: set[str] = set()

    for raw in raw_forms:
        form_key = str(raw.get("form_key") or "").strip()
        if not form_key or form_key in seen_keys:
            continue
        seen_keys.add(form_key)
        attrs = {k: v for k, v in dict(raw.get("attributes") or {}).items() if v not in (None, "", False)}
        forms.append(
            FormSnapshot(
                form_key=form_key,
                name=str(raw.get("name") or form_key),
                action=str(raw.get("action") or "") or None,
                method=str(raw.get("method") or "get").lower(),
                attributes=attrs,
                field_xpaths=[str(xpath) for xpath in (raw.get("field_xpaths") or []) if xpath],
            )
        )
    return forms


def link_elements_to_forms(elements: list[ElementSnapshot], forms: list[FormSnapshot]) -> None:
    """Attach `form_key` to elements that belong to a detected form."""
    xpath_to_form: dict[str, str] = {}
    for form in forms:
        for xpath in form.field_xpaths:
            xpath_to_form[xpath] = form.form_key

    for element in elements:
        xpath = element.xpath_fallback
        if not xpath:
            continue
        form_key = xpath_to_form.get(xpath)
        if form_key:
            element.attributes["form_key"] = form_key


def score_form_risk(form: FormSnapshot, *, field_count: int) -> int:
    """Simple form risk heuristic for AppMap export."""
    score = 20
    if form.method not in {"", "get"}:
        score += 25
    if field_count >= 4:
        score += 10
    if field_count >= 8:
        score += 10
    name_blob = f"{form.name} {form.action or ''}".lower()
    if any(kw in name_blob for kw in ("login", "register", "payment", "checkout", "password")):
        score += 20
    return max(0, min(100, score))
