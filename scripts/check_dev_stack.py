#!/usr/bin/env python3
"""Quick check that API, DB, and Redis are reachable for local dev."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request


def main() -> int:
    print("check:dev-stack")
    try:
        with urllib.request.urlopen("http://127.0.0.1:3001/health", timeout=5) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.URLError as exc:
        print("FAIL API not reachable on http://127.0.0.1:3001", file=sys.stderr)
        print("  → From project root: pnpm dev:api", file=sys.stderr)
        print(f"  → Detail: {exc}", file=sys.stderr)
        return 1

    status = body.get("status")
    db = body.get("db")
    redis = body.get("redis")
    print(f"OK API status={status} db={db} redis={redis}")

    if db != "ok":
        print("FAIL PostgreSQL — check DATABASE_URL in .env and run: brew services start postgresql@17", file=sys.stderr)
        return 1
    if redis != "ok":
        print("FAIL Redis — run: brew services start redis", file=sys.stderr)
        return 1

    print("check:dev-stack OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
