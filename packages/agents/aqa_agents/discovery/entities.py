"""Rule-based data entity inference for AppMap v3 (DISCOVERY-AGENT-VISION-SPEC §9.2)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from aqa_agents.discovery.flows import _module_key
from aqa_agents.discovery.module_tree import _page_module_map, _slugify
from aqa_shared.discovery.confidence import attach_confidence
from aqa_shared.llm.settings import estimate_cost_usd, llm_available, openai_api_key, openai_model

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "entities.v1.txt"
_MAX_ENTITIES_DEFAULT = 40
_PII_FIELD_KEYWORDS = frozenset(
    {"password", "email", "phone", "ssn", "card", "credit", "token", "secret", "pin"}
)
_CRUD_METHODS = {
    "POST": "create",
    "GET": "read",
    "HEAD": "read",
    "OPTIONS": "read",
    "PUT": "update",
    "PATCH": "update",
    "DELETE": "delete",
}


def _singularize(slug: str) -> str:
    token = (slug or "").strip().lower()
    if not token:
        return "entity"
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("s") and len(token) > 3 and not token.endswith("ss"):
        return token[:-1]
    return token


def _entity_slug(label: str) -> str:
    return _singularize(_slugify(label))


def _humanize_entity(entity_id: str) -> str:
    return entity_id.replace("-", " ").replace("_", " ").strip().title() or "Entity"


def _empty_crud_surfaces() -> dict[str, dict[str, list[str]]]:
    return {
        "create": {"page_ids": [], "form_ids": [], "api_endpoint_ids": []},
        "read": {"page_ids": [], "form_ids": [], "api_endpoint_ids": []},
        "update": {"page_ids": [], "form_ids": [], "api_endpoint_ids": []},
        "delete": {"page_ids": [], "form_ids": [], "api_endpoint_ids": []},
    }


def _add_surface(
    surfaces: dict[str, dict[str, list[str]]],
    operation: str,
    *,
    page_id: str | None = None,
    form_id: str | None = None,
    api_endpoint_id: str | None = None,
) -> None:
    bucket = surfaces.get(operation)
    if bucket is None:
        return
    if page_id and page_id not in bucket["page_ids"]:
        bucket["page_ids"].append(page_id)
    if form_id and form_id not in bucket["form_ids"]:
        bucket["form_ids"].append(form_id)
    if api_endpoint_id and api_endpoint_id not in bucket["api_endpoint_ids"]:
        bucket["api_endpoint_ids"].append(api_endpoint_id)


def _entity_from_api_path(path_pattern: str) -> str | None:
    segments = [segment for segment in str(path_pattern or "").split("/") if segment and segment != "{id}"]
    if not segments:
        return None
    if segments[0].lower() == "api" and len(segments) >= 2:
        return _entity_slug(segments[-1])
    return _entity_slug(segments[-1])


def _entity_from_openapi(endpoint: dict[str, Any]) -> str | None:
    for schema in (endpoint.get("request_schema") or {}, endpoint.get("response_schema") or {}):
        if not isinstance(schema, dict):
            continue
        ref = schema.get("$ref") or ""
        if isinstance(ref, str) and ref:
            name = ref.rsplit("/", 1)[-1]
            if name:
                return _entity_slug(name)
        components = schema.get("components", {}).get("schemas", {}) if isinstance(schema.get("components"), dict) else {}
        for name in components.keys():
            if isinstance(name, str) and name:
                return _entity_slug(name)
    return None


def _entity_from_field_name(field_name: str) -> str | None:
    token = str(field_name or "").strip().lower()
    if not token:
        return None
    if "_" in token:
        return _entity_slug(token.split("_", 1)[0])
    for suffix in ("id", "name", "email", "status", "type"):
        if token.endswith(suffix) and len(token) > len(suffix) + 1:
            return _entity_slug(token[: -len(suffix)])
    return None


def _entity_from_title(title: str) -> str | None:
    text = str(title or "").strip()
    if not text:
        return None
    match = re.search(
        r"\b(create|edit|update|delete|manage|list|view|add)\s+([A-Za-z][A-Za-z0-9 _-]{1,40})\b",
        text,
        re.I,
    )
    if match:
        return _entity_slug(match.group(2))
    words = [word for word in re.findall(r"[A-Za-z]{3,}", text)]
    if len(words) == 1:
        return _entity_slug(words[0])
    return None


def _schema_field_names(endpoint: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for schema in (endpoint.get("request_schema") or {}, endpoint.get("response_schema") or {}):
        if not isinstance(schema, dict):
            continue
        content = schema.get("content") if "content" in schema else schema
        if isinstance(content, dict):
            for media in content.values():
                if not isinstance(media, dict):
                    continue
                props = (media.get("schema") or {}).get("properties") or {}
                if isinstance(props, dict):
                    names.extend(str(key) for key in props.keys())
    for key in endpoint.get("body_keys") or []:
        names.append(str(key))
    return names


def _form_field_names(form: dict[str, Any], elements: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    attrs = form.get("attributes") or {}
    if attrs.get("name"):
        names.append(str(attrs["name"]))
    form_id = str(form.get("form_id") or "")
    field_ids = {str(item) for item in (form.get("field_element_ids") or [])}
    for element in elements:
        element_id = str(element.get("element_id") or "")
        if element_id not in field_ids:
            continue
        for key in ("text_content", "name"):
            value = element.get(key) or (element.get("attributes") or {}).get(key)
            if value:
                names.append(str(value))
        attrs = element.get("attributes") or {}
        if attrs.get("name"):
            names.append(str(attrs["name"]))
    return names


def _entity_confidence(source_types: set[str]) -> tuple[float, list[str]]:
    base = 0.6
    score = base + min(0.35, 0.1 * len(source_types))
    factors = [f"rule:source_count={len(source_types)}"]
    for source in sorted(source_types):
        factors.append(f"rule:{source}")
    return min(0.95, round(score, 3)), factors


def _entity_risk(fields: list[str], surfaces: dict[str, dict[str, list[str]]]) -> tuple[int, str]:
    risk = 20
    factors: list[str] = []
    lowered = {field.lower() for field in fields}
    if lowered & _PII_FIELD_KEYWORDS:
        risk += 25
        factors.append("pii_fields")
    if surfaces["create"]["api_endpoint_ids"] or surfaces["update"]["api_endpoint_ids"]:
        risk += 15
        factors.append("mutating_api")
    if surfaces["delete"]["api_endpoint_ids"]:
        risk += 20
        factors.append("delete_api")
    return max(0, min(100, risk)), factors[0] if factors else "baseline"


def _infer_module_id(
    entity_pages: set[str],
    page_modules: dict[str, str],
    modules: list[dict[str, Any]],
) -> str | None:
    counts: dict[str, int] = {}
    for page_id in entity_pages:
        module_id = page_modules.get(page_id)
        if module_id:
            counts[module_id] = counts.get(module_id, 0) + 1
    if counts:
        return max(counts.items(), key=lambda item: item[1])[0]
    for module in modules:
        module_id = str(module.get("module_id") or "")
        module_pages = {str(page_id) for page_id in (module.get("pages") or [])}
        if module_pages & entity_pages:
            return module_id
    return None


class _EntityBuilder:
    def __init__(self) -> None:
        self._entities: dict[str, dict[str, Any]] = {}

    def _get(self, entity_id: str) -> dict[str, Any]:
        existing = self._entities.get(entity_id)
        if existing is not None:
            return existing
        created = {
            "entity_id": entity_id,
            "name": _humanize_entity(entity_id),
            "fields": [],
            "module_id": None,
            "business_criticality": "medium",
            "risk_score": 20,
            "sources": set(),
            "crud_surfaces": _empty_crud_surfaces(),
            "_pages": set(),
        }
        self._entities[entity_id] = created
        return created

    def note(
        self,
        entity_id: str,
        *,
        source: str,
        fields: list[str] | None = None,
        page_id: str | None = None,
        form_id: str | None = None,
        api_endpoint_id: str | None = None,
        operation: str | None = None,
    ) -> None:
        slug = _entity_slug(entity_id)
        row = self._get(slug)
        row["sources"].add(source)
        for field in fields or []:
            cleaned = str(field).strip()
            if cleaned and cleaned not in row["fields"]:
                row["fields"].append(cleaned)
        if page_id:
            row["_pages"].add(str(page_id))
        if operation:
            _add_surface(
                row["crud_surfaces"],
                operation,
                page_id=page_id,
                form_id=form_id,
                api_endpoint_id=api_endpoint_id,
            )

    def build(
        self,
        *,
        page_modules: dict[str, str],
        modules: list[dict[str, Any]],
        api_ui_mappings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        mapping_by_endpoint: dict[str, list[dict[str, Any]]] = {}
        for mapping in api_ui_mappings:
            endpoint_id = str(mapping.get("api_endpoint_id") or "")
            if endpoint_id:
                mapping_by_endpoint.setdefault(endpoint_id, []).append(mapping)

        output: list[dict[str, Any]] = []
        for entity_id in sorted(self._entities.keys()):
            row = self._entities[entity_id]
            module_id = _infer_module_id(row["_pages"], page_modules, modules)
            risk_score, _ = _entity_risk(row["fields"], row["crud_surfaces"])
            confidence, factors = _entity_confidence(set(row["sources"]))
            item = {
                "entity_id": entity_id,
                "name": row["name"],
                "fields": sorted(row["fields"])[:50],
                "module_id": module_id,
                "business_criticality": "medium",
                "risk_score": risk_score,
                "crud_surfaces": row["crud_surfaces"],
            }
            output.append(attach_confidence(item, confidence=confidence, factors=factors))
        return output


def build_entities_rule_pass(
    *,
    pages: list[dict[str, Any]],
    elements: list[dict[str, Any]],
    forms: list[dict[str, Any]],
    api_endpoints: list[dict[str, Any]],
    modules: list[dict[str, Any]],
    api_ui_mappings: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Infer data entities from REST paths, forms, pages, modules, and table headers."""
    api_ui_mappings = api_ui_mappings or []
    page_modules = _page_module_map(pages)
    builder = _EntityBuilder()

    for endpoint in api_endpoints:
        entity_id = _entity_from_api_path(str(endpoint.get("path_pattern") or endpoint.get("path") or ""))
        if entity_id is None:
            entity_id = _entity_from_openapi(endpoint)
        if entity_id is None:
            continue
        method = str(endpoint.get("method") or "GET").upper()
        operation = _CRUD_METHODS.get(method, "read")
        seen_pages = [str(page_id) for page_id in (endpoint.get("seen_on_page_ids") or [])]
        if endpoint.get("first_seen_page_id"):
            seen_pages.append(str(endpoint.get("first_seen_page_id")))
        page_id = seen_pages[0] if seen_pages else None
        source = "openapi" if str(endpoint.get("source") or "") in {"openapi", "both"} else "api"
        builder.note(
            entity_id,
            source=source,
            fields=_schema_field_names(endpoint),
            page_id=page_id,
            api_endpoint_id=str(endpoint.get("endpoint_id") or "") or None,
            operation=operation,
        )

    for form in forms:
        attrs = form.get("attributes") or {}
        label = str(attrs.get("name") or attrs.get("form_key") or "")
        entity_id = _entity_from_title(label) or _entity_from_field_name(label)
        if entity_id is None:
            for field in _form_field_names(form, elements):
                entity_id = _entity_from_field_name(field)
                if entity_id:
                    break
        if entity_id is None:
            continue
        method = str(form.get("method") or "get").upper()
        operation = "create" if method == "POST" else "read"
        builder.note(
            entity_id,
            source="form",
            fields=_form_field_names(form, elements),
            page_id=str(form.get("page_id") or "") or None,
            form_id=str(form.get("form_id") or "") or None,
            operation=operation,
        )

    for page in pages:
        entity_id = _entity_from_title(str(page.get("title") or ""))
        if entity_id is None:
            continue
        builder.note(
            entity_id,
            source="page_title",
            page_id=str(page.get("page_id") or "") or None,
            operation="read",
        )

    for module in modules:
        entity_id = _entity_slug(str(module.get("name") or module.get("module_id") or ""))
        if entity_id in {"root", "app", "home", "dashboard"}:
            continue
        builder.note(
            entity_id,
            source="module",
            page_id=str((module.get("pages") or [None])[0]) if module.get("pages") else None,
            operation="read",
        )

    for element in elements:
        tag = str(element.get("tag_name") or "").lower()
        role = str(element.get("role") or "").lower()
        if tag not in {"th"} and role not in {"columnheader"}:
            continue
        label = str(element.get("text_content") or "").strip()
        entity_id = _entity_from_field_name(label) or _entity_slug(label)
        if not entity_id or entity_id == "entity":
            continue
        builder.note(
            entity_id,
            source="table_header",
            fields=[label] if label else [],
            page_id=str(element.get("page_id") or "") or None,
            operation="read",
        )

    for mapping in api_ui_mappings:
        endpoint_id = str(mapping.get("api_endpoint_id") or "")
        page_id = str(mapping.get("page_id") or "") or None
        form_id = str(mapping.get("form_id") or "") or None
        if not endpoint_id:
            continue
        endpoint = next(
            (item for item in api_endpoints if str(item.get("endpoint_id")) == endpoint_id),
            None,
        )
        if endpoint is None:
            continue
        entity_id = _entity_from_api_path(str(endpoint.get("path_pattern") or ""))
        if entity_id is None:
            continue
        operation = _CRUD_METHODS.get(str(endpoint.get("method") or "GET").upper(), "read")
        builder.note(
            entity_id,
            source="api_ui_mapping",
            page_id=page_id,
            form_id=form_id,
            api_endpoint_id=endpoint_id,
            operation=operation,
        )

    return builder.build(
        page_modules=page_modules,
        modules=modules,
        api_ui_mappings=api_ui_mappings,
    )


def link_flows_to_modules(
    flows: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    modules: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Attach module_id to flows from explicit module label or first grounded page."""
    page_modules = _page_module_map(pages)
    module_page_map: dict[str, str] = {}
    for module in modules or []:
        module_id = str(module.get("module_id") or "")
        if not module_id:
            continue
        for page_id in module.get("pages") or []:
            module_page_map[str(page_id)] = module_id
    module_ids = {str(module.get("module_id")) for module in (modules or []) if module.get("module_id")}
    linked: list[dict[str, Any]] = []
    for flow in flows:
        enriched = dict(flow)
        module_id = None
        if flow.get("module"):
            module_id = _slugify(str(flow.get("module")))
        if module_id is None:
            for step in flow.get("steps") or []:
                if not isinstance(step, dict):
                    continue
                page_id = step.get("page_id")
                if page_id and str(page_id) in module_page_map:
                    module_id = module_page_map[str(page_id)]
                    break
                if page_id and str(page_id) in page_modules:
                    module_id = page_modules[str(page_id)]
                    break
                url = step.get("url")
                if url:
                    module_id = _module_key(str(url))
                    break
        if module_id and module_ids and module_id not in module_ids:
            module_id = None
        if module_id:
            enriched["module_id"] = module_id
        linked.append(enriched)
    return linked


def _compact_entities(entities: list[dict[str, Any]], *, limit: int = 40) -> str:
    payload = [
        {
            "entity_id": entity.get("entity_id"),
            "name": entity.get("name"),
            "fields": entity.get("fields") or [],
            "module_id": entity.get("module_id"),
        }
        for entity in entities[:limit]
    ]
    return json.dumps(payload, separators=(",", ":"))


def load_entities_prompt_template() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _render_entities_prompt(*, rule_entities: list[dict[str, Any]]) -> str:
    template = load_entities_prompt_template()
    return template.replace("{{rule_entities_json}}", _compact_entities(rule_entities))


def validate_llm_entities(
    llm_entities: list[dict[str, Any]],
    *,
    rule_entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep LLM entity renames/synonyms grounded to rule entity ids and field names."""
    rule_by_id = {str(entity.get("entity_id")): entity for entity in rule_entities if entity.get("entity_id")}
    accepted: list[dict[str, Any]] = []
    for entity in llm_entities:
        if not isinstance(entity, dict):
            continue
        entity_id = str(entity.get("entity_id") or "")
        rule_entity = rule_by_id.get(entity_id)
        if rule_entity is None:
            continue
        allowed_fields = {str(field).lower() for field in (rule_entity.get("fields") or [])}
        fields_in = entity.get("fields") if isinstance(entity.get("fields"), list) else rule_entity.get("fields")
        grounded_fields = [
            str(field)
            for field in (fields_in or [])
            if str(field).lower() in allowed_fields
        ]
        if not grounded_fields:
            grounded_fields = list(rule_entity.get("fields") or [])
        merged = dict(rule_entity)
        merged["name"] = str(entity.get("name") or rule_entity.get("name"))[:255]
        merged["fields"] = grounded_fields
        confidence = min(0.9, float(rule_entity.get("confidence") or 0.8) + 0.05)
        factors = list(rule_entity.get("confidence_factors") or [])
        factors.append("llm:synonym_pass")
        accepted.append(attach_confidence(merged, confidence=confidence, factors=factors))
    if not accepted:
        return rule_entities
    accepted_ids = {entity["entity_id"] for entity in accepted}
    for rule_entity in rule_entities:
        if rule_entity["entity_id"] not in accepted_ids:
            accepted.append(rule_entity)
    return sorted(accepted, key=lambda item: str(item.get("entity_id")))


def structure_entities_with_llm(
    *,
    rule_entities: list[dict[str, Any]],
    use_llm: bool,
    token_budget_remaining: int,
    llm_stage: str = "entities",
) -> tuple[list[dict[str, Any]], int, float, str | None]:
    """Return (entities, tokens_used, cost_estimate, skip_reason)."""
    if not rule_entities:
        return [], 0, 0.0, "no rule entities"
    if not use_llm:
        return rule_entities, 0, 0.0, "use_llm=false"
    if not llm_available(use_llm=True):
        return rule_entities, 0, 0.0, "OPENAI_API_KEY unset"
    if token_budget_remaining <= 0:
        return rule_entities, 0, 0.0, f"{llm_stage} budget exhausted"

    prompt = _render_entities_prompt(rule_entities=rule_entities)
    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai package not installed; skipping entity LLM structuring")
        return rule_entities, 0, 0.0, "openai package missing"

    client = OpenAI(api_key=openai_api_key())
    model = openai_model()
    try:
        response = client.chat.completions.create(
            model=model,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You output strict JSON only for AppMap data entity naming.",
                },
                {"role": "user", "content": prompt},
            ],
        )
    except Exception as exc:
        logger.warning("DiscoveryAgent LLM entity structuring failed; using rule-based entities", exc_info=exc)
        return rule_entities, 0, 0.0, str(exc)

    content = (response.choices[0].message.content or "").strip()
    tokens_used = int(response.usage.total_tokens if response.usage else 0)
    cost_estimate = estimate_cost_usd(model=model, tokens=tokens_used)
    try:
        payload = json.loads(content)
        llm_entities = payload.get("data_entities") or payload.get("entities") or []
        if not isinstance(llm_entities, list):
            raise ValueError("entities payload is not a list")
        accepted = validate_llm_entities(llm_entities, rule_entities=rule_entities)
        return accepted, tokens_used, cost_estimate, None
    except Exception as exc:
        logger.warning("DiscoveryAgent LLM entity JSON invalid; using rule-based entities", exc_info=exc)
        return rule_entities, tokens_used, cost_estimate, str(exc)
