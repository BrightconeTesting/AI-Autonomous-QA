"""Hard safety exclusions always enforced during crawl (SPEC §15.2, Day 17)."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from aqa_discovery.url_utils import is_excluded_url

# Always-on glob patterns merged with user excluded_urls at crawl time.
HARD_EXCLUDED_URL_PATTERNS: tuple[str, ...] = (
    "**/logout**",
    "**/sign-out**",
    "**/signout**",
    "**/sign_out**",
    "**/delete-account**",
    "**/delete_account**",
    "**/close-account**",
    "**/close_account**",
    "**/deactivate**",
)

_DANGEROUS_PATH_MARKERS: tuple[str, ...] = (
    "logout",
    "sign-out",
    "signout",
    "sign_out",
    "delete-account",
    "delete_account",
    "close-account",
    "close_account",
    "deactivate",
)

_DANGEROUS_LINK_TEXT = re.compile(
    r"\b(log\s*out|sign\s*out|delete\s+account|close\s+account|deactivate(?:\s+account)?)\b",
    re.IGNORECASE,
)


def is_safety_excluded_url(url: str) -> bool:
    """Return True when a URL must never be visited or enqueued."""
    if is_excluded_url(url, list(HARD_EXCLUDED_URL_PATTERNS)):
        return True

    parsed = urlparse(url)
    path_lower = (parsed.path or "/").lower()
    for marker in _DANGEROUS_PATH_MARKERS:
        if marker in path_lower:
            return True
    if "/delete" in path_lower and "allowlist" not in path_lower:
        return True
    return False


def is_safety_excluded_link(*, href: str, link_text: str = "") -> bool:
    """Return True when an extracted anchor should not be enqueued."""
    if is_safety_excluded_url(href):
        return True
    if link_text and _DANGEROUS_LINK_TEXT.search(link_text.strip()):
        return True
    return False
