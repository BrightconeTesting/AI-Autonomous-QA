#!/usr/bin/env python3
"""Verify GET /metrics returns Prometheus text with default + queue gauges."""

import sys

from fastapi.testclient import TestClient

from aqa_api.main import app


def main() -> int:
    print("verify:metrics")
    client = TestClient(app)

    resp = client.get("/metrics")
    if resp.status_code != 200:
        print(f"FAIL: status={resp.status_code}", file=sys.stderr)
        return 1

    body = resp.text
    # Python prometheus_client exposes GC/info metrics; process_cpu_* is Linux-only.
    required = ("python_info", "aqa_queue_depth", "aqa_crawl_time_seconds")
    missing = [name for name in required if name not in body]
    if missing:
        print(f"FAIL: missing metrics: {missing}", file=sys.stderr)
        return 1

    if "text/plain" not in resp.headers.get("content-type", ""):
        print(f"FAIL: unexpected content-type: {resp.headers.get('content-type')}", file=sys.stderr)
        return 1

    print("OK /metrics: python_info present")
    print("OK /metrics: aqa_queue_depth gauge present")
    print("OK /metrics: aqa_crawl_time_seconds histogram present")
    print("verify:metrics OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
