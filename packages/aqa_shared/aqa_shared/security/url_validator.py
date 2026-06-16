"""SSRF and unsafe URL validation (SPEC §23.3, Day 12)."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class UrlSecurityError(ValueError):
    """Raised when a URL targets a blocked host or network range."""


BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "metadata.goog",
    }
)


def _is_blocked_ip(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def _check_ip_literal(hostname: str) -> None:
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        return
    if _is_blocked_ip(addr):
        raise UrlSecurityError("URL resolves to a private or reserved IP address")


def _resolve_and_check(hostname: str, port: int | None) -> None:
    try:
        infos = socket.getaddrinfo(
            hostname,
            port or 443,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror as exc:
        raise UrlSecurityError(f"could not resolve hostname {hostname!r}") from exc

    for info in infos:
        ip_str = info[4][0]
        addr = ipaddress.ip_address(ip_str)
        if _is_blocked_ip(addr):
            raise UrlSecurityError("URL resolves to a private or reserved IP address")


def validate_url_safe(url: str) -> str:
    """Validate HTTP(S) URL is safe for outbound crawl targets. Returns normalized input."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UrlSecurityError("URL must use http or https")
    hostname = parsed.hostname
    if not hostname:
        raise UrlSecurityError("URL must include a hostname")

    host = hostname.lower().rstrip(".")
    if host in BLOCKED_HOSTNAMES:
        raise UrlSecurityError("URL hostname is not allowed")

    _check_ip_literal(host)
    try:
        ipaddress.ip_address(host)
    except ValueError:
        _resolve_and_check(host, parsed.port)

    return url


def validate_urls_safe(urls: list[str]) -> None:
    for url in urls:
        validate_url_safe(url)
