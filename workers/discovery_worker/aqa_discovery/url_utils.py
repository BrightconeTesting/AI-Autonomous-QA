"""URL normalization and crawl scope checks (Day 16)."""

from __future__ import annotations

import fnmatch
from urllib.parse import urljoin, urlparse, urlunparse


def normalize_crawl_url(url: str) -> str:
    """Canonical URL for visited-set dedupe (SPEC §15.3 hash-SPA aware)."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return url.strip()

    host = parsed.hostname.lower()
    port = parsed.port
    default_port = 443 if parsed.scheme == "https" else 80
    netloc = host if port in (None, default_port) else f"{host}:{port}"

    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    fragment = parsed.fragment
    if fragment and (fragment.startswith("/") or fragment.startswith("!")):
        return urlunparse((parsed.scheme.lower(), netloc, path, "", "", fragment))

    if parsed.query:
        return urlunparse((parsed.scheme.lower(), netloc, path, "", parsed.query, ""))
    return urlunparse((parsed.scheme.lower(), netloc, path, "", "", ""))


def is_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.hostname)


def is_crawl_seed_url(url: str) -> bool:
    """True for HTTP(S) pages and local file:// fixtures used in verify scripts."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme == "file":
        return bool(parsed.path)
    return parsed.scheme in ("http", "https") and bool(parsed.hostname)


def is_allowed_domain(url: str, allowed_domains: set[str]) -> bool:
    if not allowed_domains:
        return True
    parsed = urlparse(url)
    if parsed.scheme == "file":
        return True
    hostname = parsed.hostname
    if not hostname:
        return False
    return hostname.lower() in allowed_domains


def is_excluded_url(url: str, patterns: list[str]) -> bool:
    if not patterns:
        return False
    parsed = urlparse(url)
    path = parsed.path or "/"
    path_with_query = f"{path}?{parsed.query}" if parsed.query else path
    candidates = [url, path, path_with_query]
    for pattern in patterns:
        for candidate in candidates:
            if fnmatch.fnmatch(candidate, pattern) or fnmatch.fnmatch(candidate.lower(), pattern.lower()):
                return True
    return False


def resolve_link(page_url: str, href: str) -> str | None:
    if not href or href.startswith(("javascript:", "mailto:", "tel:", "data:")):
        return None
    absolute = urljoin(page_url, href)
    if not is_http_url(absolute):
        return None
    return absolute
