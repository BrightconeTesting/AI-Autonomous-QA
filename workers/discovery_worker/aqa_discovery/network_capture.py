"""Playwright network capture for API endpoint discovery (§8.3)."""

from __future__ import annotations

import hashlib
import re
import time
from typing import Any
from urllib.parse import urlparse

from aqa_discovery.api_types import ApiEndpointSnapshot, NetworkEventSnapshot
from aqa_shared.discovery.api_ui_mapper import extract_body_keys

_STATIC_EXTENSIONS = (
    ".js",
    ".css",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".map",
)
_DEFAULT_ANALYTICS_HOSTS = (
    "google-analytics.com",
    "googletagmanager.com",
    "segment.io",
    "segment.com",
    "hotjar.com",
    "facebook.net",
    "doubleclick.net",
)
_INCLUDED_RESOURCE_TYPES = {"xhr", "fetch"}
_OPTIONAL_RESOURCE_TYPES = {"document"}
_SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "x-auth-token",
        "proxy-authorization",
    }
)
_UUID_SEGMENT = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.I,
)
_NUMERIC_SEGMENT = re.compile(r"^\d+$")


def normalize_api_path(url: str) -> tuple[str, str]:
    """Return observed path and normalized path_pattern."""
    parsed = urlparse(url)
    raw_path = parsed.path or "/"
    segments: list[str] = []
    for segment in raw_path.split("/"):
        if not segment:
            continue
        if _UUID_SEGMENT.match(segment) or _NUMERIC_SEGMENT.match(segment):
            segments.append("{id}")
        else:
            segments.append(segment)
    if not segments:
        return raw_path, raw_path
    pattern = "/" + "/".join(segments)
    return raw_path, pattern


def _sanitize_headers(headers: dict[str, str] | None) -> dict[str, str]:
    if not headers:
        return {}
    cleaned: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in _SENSITIVE_HEADERS:
            continue
        cleaned[key] = str(value)[:500]
    return cleaned


def _hash_body(body: str | bytes | None) -> str | None:
    if body is None:
        return None
    if isinstance(body, str):
        payload = body.encode("utf-8", errors="ignore")
    else:
        payload = body
    if not payload:
        return None
    return hashlib.sha256(payload).hexdigest()


def _is_static_asset(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in _STATIC_EXTENSIONS)


def _is_analytics_host(url: str, excluded_hosts: list[str]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    blocked = {item.lower() for item in excluded_hosts} | set(_DEFAULT_ANALYTICS_HOSTS)
    return any(host == blocked_host or host.endswith(f".{blocked_host}") for blocked_host in blocked)


class NetworkCapture:
    """Collect xhr/fetch requests for a single page visit."""

    def __init__(
        self,
        *,
        page_url: str,
        allowed_domains: list[str] | None = None,
        include_document: bool = False,
        excluded_analytics_domains: list[str] | None = None,
    ) -> None:
        self.page_url = page_url
        self.allowed_domains = [domain.lower() for domain in (allowed_domains or [])]
        self.include_document = include_document
        self.excluded_analytics_domains = list(excluded_analytics_domains or [])
        self._endpoints: dict[str, ApiEndpointSnapshot] = {}
        self._network_events: list[NetworkEventSnapshot] = []
        self._har_entries: list[dict[str, Any]] = []
        self._session_start = time.monotonic()

    def attach(self, page) -> None:
        page.on("request", self._on_request)
        page.on("response", self._on_response)

    def detach(self, page) -> None:
        page.remove_listener("request", self._on_request)
        page.remove_listener("response", self._on_response)

    def collect(self) -> list[ApiEndpointSnapshot]:
        return list(self._endpoints.values())

    def network_events(self) -> list[NetworkEventSnapshot]:
        return list(self._network_events)

    def har_entries(self) -> list[dict[str, Any]]:
        return list(self._har_entries)

    def _should_capture(self, *, url: str, resource_type: str | None) -> bool:
        if not url.startswith(("http://", "https://")):
            return False
        if _is_static_asset(url):
            return False
        if _is_analytics_host(url, self.excluded_analytics_domains):
            return False
        if resource_type in _INCLUDED_RESOURCE_TYPES:
            return True
        if self.include_document and resource_type in _OPTIONAL_RESOURCE_TYPES:
            return True
        return False

    def _dedup_key(self, method: str, url: str) -> str:
        _path, pattern = normalize_api_path(url)
        return f"{method.upper()} {pattern}"

    def _on_request(self, request) -> None:
        try:
            resource_type = request.resource_type
            url = request.url
            if not self._should_capture(url=url, resource_type=resource_type):
                return
            method = str(request.method or "GET").upper()
            key = self._dedup_key(method, url)
            path, pattern = normalize_api_path(url)
            body_hash = None
            body_keys: list[str] = []
            try:
                body_hash = _hash_body(request.post_data)
                body_keys = extract_body_keys(request.post_data)
            except Exception:
                body_hash = None
            headers = _sanitize_headers(request.headers)
            timestamp_ms = (time.monotonic() - self._session_start) * 1000.0
            self._network_events.append(
                NetworkEventSnapshot(
                    method=method,
                    path=path,
                    path_pattern=pattern,
                    url=url,
                    timestamp_ms=timestamp_ms,
                    body_keys=body_keys,
                    resource_type=resource_type,
                )
            )
            existing = self._endpoints.get(key)
            if existing is not None:
                existing.seen_count += 1
                if body_keys and not existing.body_keys:
                    existing.body_keys = body_keys
                return
            self._endpoints[key] = ApiEndpointSnapshot(
                method=method,
                path=path,
                path_pattern=pattern,
                url=url,
                resource_type=resource_type,
                request_headers=headers,
                body_hash=body_hash,
                body_keys=body_keys,
                source="network",
            )
        except Exception:
            return

    def _on_response(self, response) -> None:
        try:
            request = response.request
            resource_type = request.resource_type
            url = request.url
            if not self._should_capture(url=url, resource_type=resource_type):
                return
            key = self._dedup_key(str(request.method or "GET").upper(), url)
            endpoint = self._endpoints.get(key)
            if endpoint is None:
                return
            endpoint.status = int(response.status)
            if self._har_entries is not None:
                self._har_entries.append(
                    {
                        "method": endpoint.method,
                        "url": url,
                        "path": endpoint.path,
                        "path_pattern": endpoint.path_pattern,
                        "status": endpoint.status,
                        "resource_type": resource_type,
                        "page_url": self.page_url,
                    }
                )
        except Exception:
            return


def merge_api_endpoints(
    *groups: list[ApiEndpointSnapshot],
) -> list[ApiEndpointSnapshot]:
    """Merge endpoint lists by method + path_pattern."""
    merged: dict[str, ApiEndpointSnapshot] = {}
    for group in groups:
        for endpoint in group:
            key = f"{endpoint.method.upper()} {endpoint.path_pattern}"
            existing = merged.get(key)
            if existing is None:
                merged[key] = endpoint.model_copy(deep=True)
                continue
            existing.seen_count += endpoint.seen_count
            if existing.source == "network" and endpoint.source == "openapi":
                existing.source = "both"
                existing.request_schema = endpoint.request_schema or existing.request_schema
                existing.response_schema = endpoint.response_schema or existing.response_schema
            elif existing.source == "openapi" and endpoint.source == "network":
                existing.source = "both"
            if endpoint.status is not None:
                existing.status = endpoint.status
    return list(merged.values())
