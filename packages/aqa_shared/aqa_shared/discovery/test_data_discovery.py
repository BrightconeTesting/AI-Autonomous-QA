"""Test data catalog builder (DISCOVERY-AGENT-VISION-SPEC §8.10)."""

from __future__ import annotations

import re
import uuid
from typing import Any

PII_CLASSES = {
    "email": "email",
    "phone": "phone",
    "password": "password",
    "ssn": "ssn",
    "card": "payment",
    "credit": "payment",
    "cvv": "payment",
}


def _pii_class(field_name: str, data_type: str) -> str | None:
    blob = f"{field_name} {data_type}".lower()
    for keyword, label in PII_CLASSES.items():
        if keyword in blob:
            return label
    return None


def _suggested_safe_value(
    *,
    field_name: str,
    data_type: str,
    run_token: str,
    constraints: dict[str, Any],
) -> str:
    lowered = field_name.lower()
    if data_type == "password" or "password" in lowered:
        return "***"
    if data_type == "email" or "email" in lowered:
        return f"qa-test-{run_token}@example.com"
    if data_type == "tel" or "phone" in lowered:
        return "5550100199"
    if data_type in {"number", "integer"}:
        return str(constraints.get("min") or "1")
    if data_type == "date":
        return "2026-01-15"
    if data_type == "url":
        return f"https://example.com/qa-{run_token}"
    return f"qa-{run_token}-{lowered[:24] or 'value'}"


def _field_from_element(element: dict[str, Any], *, run_token: str) -> dict[str, Any] | None:
    attrs = dict(element.get("attributes") or {})
    html5 = dict(attrs.get("html5") or {})
    name = str(attrs.get("name") or element.get("text_content") or "").strip()
    if not name:
        return None
    data_type = str(html5.get("type") or attrs.get("type") or "text").lower()
    constraints: dict[str, Any] = {}
    for key in ("required", "pattern", "min", "max", "minlength", "maxlength"):
        if key in html5:
            constraints[key] = html5[key]
        elif attrs.get(key) is not None:
            constraints[key] = attrs.get(key)
    required = bool(constraints.get("required") or attrs.get("required"))
    return {
        "name": name,
        "data_type": data_type,
        "required": required,
        "constraints": constraints,
        "suggested_safe_value": _suggested_safe_value(
            field_name=name,
            data_type=data_type,
            run_token=run_token,
            constraints=constraints,
        ),
        "pii_class": _pii_class(name, data_type),
    }


def build_test_data_catalog(
    *,
    forms: list[dict[str, Any]],
    elements: list[dict[str, Any]],
    api_endpoints: list[dict[str, Any]],
    data_entities: list[dict[str, Any]] | None = None,
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    """Infer synthetic-safe test data fixtures from forms, fields, and API schemas."""
    run_token = re.sub(r"[^a-zA-Z0-9_-]", "", str(run_id or uuid.uuid4()))[:12]
    elements_by_id = {str(element.get("element_id") or ""): element for element in elements}
    catalog: list[dict[str, Any]] = []

    for form in forms:
        field_ids = [str(item) for item in (form.get("field_element_ids") or [])]
        fields: list[dict[str, Any]] = []
        for field_id in field_ids:
            element = elements_by_id.get(field_id)
            if element is None:
                continue
            field = _field_from_element(element, run_token=run_token)
            if field:
                fields.append(field)
        if not fields:
            continue
        catalog.append(
            {
                "catalog_id": str(uuid.uuid4()),
                "target_type": "form",
                "target_id": str(form.get("form_id") or ""),
                "fields": fields,
                "synthetic_strategy": "deterministic_fixture",
                "never_use_live_pii": True,
            }
        )

    for endpoint in api_endpoints:
        schema = endpoint.get("request_schema") or {}
        props: dict[str, Any] = {}
        if isinstance(schema, dict):
            content = schema.get("content") if "content" in schema else schema
            if isinstance(content, dict):
                for media in content.values():
                    if isinstance(media, dict):
                        props.update((media.get("schema") or {}).get("properties") or {})
        for key in endpoint.get("body_keys") or []:
            props.setdefault(str(key), {"type": "string"})
        if not props:
            continue
        fields = []
        for name, definition in props.items():
            data_type = str((definition or {}).get("type") or "string")
            fields.append(
                {
                    "name": str(name),
                    "data_type": data_type,
                    "required": str(name) in ((definition or {}).get("required") or []),
                    "constraints": {},
                    "suggested_safe_value": _suggested_safe_value(
                        field_name=str(name),
                        data_type=data_type,
                        run_token=run_token,
                        constraints={},
                    ),
                    "pii_class": _pii_class(str(name), data_type),
                }
            )
        if fields:
            catalog.append(
                {
                    "catalog_id": str(uuid.uuid4()),
                    "target_type": "api_endpoint",
                    "target_id": str(endpoint.get("endpoint_id") or ""),
                    "fields": fields,
                    "synthetic_strategy": "deterministic_fixture",
                    "never_use_live_pii": True,
                }
            )

    for entity in data_entities or []:
        entity_fields = [str(name) for name in (entity.get("fields") or [])]
        if not entity_fields:
            continue
        catalog.append(
            {
                "catalog_id": str(uuid.uuid4()),
                "target_type": "entity",
                "target_id": str(entity.get("entity_id") or ""),
                "fields": [
                    {
                        "name": name,
                        "data_type": "string",
                        "required": False,
                        "constraints": {},
                        "suggested_safe_value": _suggested_safe_value(
                            field_name=name,
                            data_type="string",
                            run_token=run_token,
                            constraints={},
                        ),
                        "pii_class": _pii_class(name, "string"),
                    }
                    for name in entity_fields
                ],
                "synthetic_strategy": "deterministic_fixture",
                "never_use_live_pii": True,
            }
        )

    return catalog
