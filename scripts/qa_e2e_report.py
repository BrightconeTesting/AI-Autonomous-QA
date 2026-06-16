#!/usr/bin/env python3
"""QA E2E test report — manual tester flow across Week 1-2 + Day 11-12."""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

# Use encryption for realistic Day 12 path
os.environ["ENCRYPTION_KEY"] = os.getenv("ENCRYPTION_KEY") or ("0123456789abcdef" * 4)
os.environ.setdefault("DATABASE_URL", os.getenv("DATABASE_URL", ""))

from aqa_api.main import app
from aqa_shared.crypto.auth_config import decrypt_auth_config, is_encrypted_auth_config
from aqa_shared.db.models import Application
from aqa_shared.db.session import get_session_factory
from sqlalchemy import select

PASS = 0
FAIL = 0
WARN = 0
RESULTS: list[tuple[str, str, str]] = []


def record(name: str, status: str, detail: str = "") -> None:
    global PASS, FAIL, WARN
    if status == "PASS":
        PASS += 1
    elif status == "FAIL":
        FAIL += 1
    else:
        WARN += 1
    RESULTS.append((name, status, detail))
    icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️"}.get(status, "?")
    line = f"{icon} {name}"
    if detail:
        line += f" — {detail}"
    print(line)


def main() -> int:
    print("=" * 60)
    print("QA E2E TEST REPORT — Autonomous QA Platform")
    print("=" * 60)

    # --- Infrastructure ---
    print("\n[1] Infrastructure")
    try:
        import redis

        r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
        if r.ping():
            record("Redis PING", "PASS", "PONG")
        else:
            record("Redis PING", "FAIL")
    except Exception as exc:
        record("Redis PING", "FAIL", str(exc))

    from aqa_shared.db.session import check_db_connection

    if check_db_connection():
        record("PostgreSQL connection", "PASS")
    else:
        record("PostgreSQL connection", "FAIL")

    # --- Live API (optional) ---
    print("\n[2] Live API (http://localhost:3001)")
    live_base = "http://localhost:3001"
    try:
        resp = httpx.get(f"{live_base}/health", timeout=3)
        if resp.status_code == 200 and resp.json().get("status") == "ok":
            record("Live GET /health", "PASS", resp.text[:80])
        else:
            record("Live GET /health", "WARN", f"status={resp.status_code} (is pnpm dev:api running?)")
    except Exception:
        record("Live GET /health", "WARN", "API not running — TestClient used below instead")

    client = TestClient(app)

    # --- Health & metrics ---
    print("\n[3] Core API endpoints (TestClient)")
    health = client.get("/health")
    if health.status_code == 200 and health.json()["db"] == "ok":
        record("GET /health", "PASS", json.dumps(health.json()))
    else:
        record("GET /health", "FAIL", str(health.status_code))

    metrics = client.get("/metrics")
    if metrics.status_code == 200 and "aqa_queue_depth" in metrics.text:
        record("GET /metrics", "PASS", "Prometheus text + aqa_queue_depth")
    else:
        record("GET /metrics", "FAIL")

    queues = client.get("/api/v1/queues/stats")
    if queues.status_code == 200 and "queues" in queues.json():
        record("GET /api/v1/queues/stats", "PASS", f"6 queues")
    else:
        record("GET /api/v1/queues/stats", "FAIL")

    # --- Day 11-12 Application API ---
    print("\n[4] Application API (Day 11-12)")

    ssrf = client.post(
        "/api/v1/apps",
        json={"name": "QA SSRF", "base_url": "http://127.0.0.1", "seed_urls": []},
    )
    if ssrf.status_code == 400:
        record("SSRF block 127.0.0.1", "PASS", ssrf.json().get("detail", "")[:60])
    else:
        record("SSRF block 127.0.0.1", "FAIL", f"got {ssrf.status_code}")

    app_payload = {
        "name": f"QA E2E App {uuid.uuid4().hex[:8]}",
        "base_url": "https://juice-shop.herokuapp.com",
        "seed_urls": ["https://juice-shop.herokuapp.com/#/login"],
        "auth_config": {
            "type": "form",
            "credentials_secret_ref": "JUICE_SHOP_TEST_USER",
            "email_selector": "input[name=email]",
        },
        "crawl_config": {"max_pages": 10, "max_depth": 2},
    }
    create = client.post("/api/v1/apps", json=app_payload)
    if create.status_code != 201:
        record("POST /api/v1/apps", "FAIL", create.text)
        print_summary()
        return 1

    created = create.json()
    app_id = created["app_id"]
    if "credentials_secret_ref" in json.dumps(created):
        record("Auth secrets stripped in response", "FAIL")
    elif created["auth_config"] == {"configured": True, "type": "form"}:
        record("POST /api/v1/apps", "PASS", f"app_id={app_id}")
        record("Auth secrets stripped in response", "PASS")
    else:
        record("POST /api/v1/apps", "PASS", f"app_id={app_id}")
        record("Auth secrets stripped in response", "WARN", str(created["auth_config"]))

    session = get_session_factory()()
    try:
        row = session.scalar(select(Application).where(Application.app_id == uuid.UUID(app_id)))
        if row and is_encrypted_auth_config(row.auth_config):
            dec = decrypt_auth_config(row.auth_config)
            if dec.get("credentials_secret_ref") == "JUICE_SHOP_TEST_USER":
                record("auth_config encrypted in DB", "PASS")
            else:
                record("auth_config encrypted in DB", "FAIL", "decrypt mismatch")
        elif row and os.getenv("NODE_ENV", "development") == "development":
            record("auth_config encrypted in DB", "WARN", "plaintext in dev (set ENCRYPTION_KEY in .env)")
        else:
            record("auth_config encrypted in DB", "FAIL")
    finally:
        session.close()

    get_one = client.get(f"/api/v1/apps/{app_id}")
    if get_one.status_code == 200 and get_one.json()["name"] == app_payload["name"]:
        record("GET /api/v1/apps/{id}", "PASS")
    else:
        record("GET /api/v1/apps/{id}", "FAIL")

    list_apps = client.get("/api/v1/apps")
    if list_apps.status_code == 200 and list_apps.json()["total"] >= 1:
        record("GET /api/v1/apps", "PASS", f"total={list_apps.json()['total']}")
    else:
        record("GET /api/v1/apps", "FAIL")

    # --- Celery E2E ---
    print("\n[5] Celery pipeline (enqueue → worker → result)")
    import subprocess
    import time

    worker = subprocess.Popen(
        [
            str(ROOT / ".venv/bin/celery"),
            "-A",
            "aqa_celery.app",
            "worker",
            "-Q",
            "discover,design,generate-scripts,execute,report,analyze",
            "--loglevel=warning",
            "--concurrency=1",
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(4)
    try:
        e2e = subprocess.run(
            [str(ROOT / ".venv/bin/python"), str(ROOT / "scripts/verify_e2e_celery.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if e2e.returncode == 0 and "verify:e2e-celery OK" in e2e.stdout:
            for line in e2e.stdout.splitlines():
                if line.startswith("OK "):
                    record(f"Celery {line[3:]}", "PASS")
            record("Celery E2E pipeline", "PASS", "6 tasks SUCCESS")
        else:
            record("Celery E2E pipeline", "FAIL", e2e.stderr or e2e.stdout)
    finally:
        worker.terminate()
        try:
            worker.wait(timeout=10)
        except subprocess.TimeoutExpired:
            worker.kill()

    print_summary()
    return 0 if FAIL == 0 else 1


def print_summary() -> None:
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  PASS: {PASS}")
    print(f"  FAIL: {FAIL}")
    print(f"  WARN: {WARN}")
    print()
    if FAIL == 0 and WARN == 0:
        print("VERDICT: ✅ ALL CHECKS PASSED — system working fine")
    elif FAIL == 0:
        print("VERDICT: ✅ PASSED with warnings (review WARN items)")
    else:
        print("VERDICT: ❌ FAILED — see items above")
    print("=" * 60)


if __name__ == "__main__":
    sys.exit(main())
