#!/usr/bin/env python3
"""Verify network capture helpers (Phase B)."""

from __future__ import annotations

import sys

from aqa_discovery.api_types import ApiEndpointSnapshot
from aqa_discovery.network_capture import (
    NetworkCapture,
    merge_api_endpoints,
    normalize_api_path,
)


def _verify_normalize_path() -> bool:
    path, pattern = normalize_api_path("https://example.com/api/users/42/profile")
    if pattern != "/api/users/{id}/profile":
        print(f"FAIL normalize path pattern={pattern}", file=sys.stderr)
        return False
    uuid_path, uuid_pattern = normalize_api_path(
        "https://example.com/api/items/550e8400-e29b-41d4-a716-446655440000"
    )
    if uuid_pattern != "/api/items/{id}":
        print(f"FAIL uuid pattern={uuid_pattern}", file=sys.stderr)
        return False
    print(f"OK normalize_api_path: {path} -> {pattern}")
    return True


def _verify_merge() -> bool:
    network = [
        ApiEndpointSnapshot(method="POST", path="/api/users", path_pattern="/api/users", source="network"),
    ]
    openapi = [
        ApiEndpointSnapshot(
            method="POST",
            path="/api/users",
            path_pattern="/api/users",
            source="openapi",
            request_schema={"type": "object"},
        )
    ]
    merged = merge_api_endpoints(network, openapi)
    if len(merged) != 1 or merged[0].source != "both":
        print(f"FAIL merge source={merged[0].source if merged else None}", file=sys.stderr)
        return False
    print("OK merge_api_endpoints marks source=both")
    return True


def _verify_sanitize_headers() -> bool:
    capture = NetworkCapture(page_url="https://example.com/app")
    capture._on_request(
        type(
            "Req",
            (),
            {
                "method": "GET",
                "url": "https://example.com/api/users",
                "resource_type": "xhr",
                "headers": {"Authorization": "Bearer secret", "Accept": "application/json"},
                "post_data": None,
            },
        )()
    )
    endpoints = capture.collect()
    if not endpoints:
        print("FAIL no endpoints captured", file=sys.stderr)
        return False
    if "Authorization" in endpoints[0].request_headers:
        print("FAIL sensitive header persisted", file=sys.stderr)
        return False
    print("OK sensitive headers stripped")
    return True


def main() -> int:
    print("verify:network-capture")
    ok = _verify_normalize_path() and _verify_merge() and _verify_sanitize_headers()
    if not ok:
        return 1
    print("verify:network-capture OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
