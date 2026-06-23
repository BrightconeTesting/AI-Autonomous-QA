"""OpenAPI 3.x import for API endpoint discovery (§8.4)."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlparse

import httpx

from aqa_discovery.api_types import ApiEndpointSnapshot
from aqa_discovery.network_capture import normalize_api_path
from aqa_shared.security.url_validator import UrlSecurityError, validate_url_safe

logger = logging.getLogger(__name__)

_OPENAPI_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


def validate_openapi_url(
    openapi_url: str,
    *,
    base_url: str,
    allowed_domains: list[str] | None = None,
) -> str:
    """SSRF-safe validation: same host as app or in allowed_domains."""
    validate_url_safe(openapi_url)
    parsed = urlparse(openapi_url)
    host = (parsed.hostname or "").lower()
    base_host = (urlparse(base_url).hostname or "").lower()
    allowed = {domain.lower() for domain in (allowed_domains or [])}
    if host != base_host and host not in allowed:
        raise UrlSecurityError(
            f"openapi_url host {host!r} must match application host or allowed_domains"
        )
    return openapi_url


def _load_openapi_document(content: bytes, *, content_type: str | None = None) -> dict[str, Any]:
    text = content.decode("utf-8", errors="replace").strip()
    if not text:
        raise ValueError("OpenAPI document is empty")
    if text.startswith("{") or "json" in (content_type or "").lower():
        data = json.loads(text)
    else:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ValueError("YAML OpenAPI requires PyYAML") from exc
        data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("OpenAPI document must be a JSON object")
    return data


def _schema_from_operation(operation: dict[str, Any], key: str) -> dict[str, Any]:
    schema = operation.get(key)
    return dict(schema) if isinstance(schema, dict) else {}


def endpoints_from_openapi(document: dict[str, Any]) -> list[ApiEndpointSnapshot]:
    """Parse OpenAPI 3.x paths into endpoint snapshots."""
    paths = document.get("paths")
    if not isinstance(paths, dict):
        return []

    endpoints: list[ApiEndpointSnapshot] = []
    for path_template, item in paths.items():
        if not isinstance(item, dict):
            continue
        path = str(path_template)
        _, pattern = normalize_api_path(f"https://example.com{path}")
        for method, operation in item.items():
            if method.lower() not in _OPENAPI_METHODS or not isinstance(operation, dict):
                continue
            endpoints.append(
                ApiEndpointSnapshot(
                    method=method.upper(),
                    path=path,
                    path_pattern=pattern,
                    source="openapi",
                    request_schema=_schema_from_operation(operation, "requestBody"),
                    response_schema={
                        str(code): body
                        for code, body in (operation.get("responses") or {}).items()
                        if isinstance(body, dict)
                    },
                )
            )
    return endpoints


def fetch_openapi_endpoints(
    openapi_url: str,
    *,
    base_url: str,
    allowed_domains: list[str] | None = None,
    timeout_sec: float = 15.0,
) -> list[ApiEndpointSnapshot]:
    """Fetch and parse an OpenAPI document into endpoint snapshots."""
    validate_openapi_url(openapi_url, base_url=base_url, allowed_domains=allowed_domains)
    try:
        response = httpx.get(openapi_url, timeout=timeout_sec, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("OpenAPI fetch failed: %s", exc)
        raise ValueError(f"Failed to fetch OpenAPI document: {exc}") from exc

    document = _load_openapi_document(response.content, content_type=response.headers.get("content-type"))
    return endpoints_from_openapi(document)
