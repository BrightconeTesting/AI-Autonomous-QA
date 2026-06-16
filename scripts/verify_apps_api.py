#!/usr/bin/env python3
"""Verify Application API — Day 11–12."""

import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import select

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# Force encryption in verify runs (override empty .env placeholder)
TEST_KEY = "0123456789abcdef" * 4  # 32 bytes hex
os.environ["ENCRYPTION_KEY"] = TEST_KEY
os.environ.setdefault("DATABASE_URL", os.getenv("DATABASE_URL", ""))
os.environ.setdefault("NODE_ENV", "development")

from aqa_api.main import app
from aqa_shared.crypto.auth_config import decrypt_auth_config, is_encrypted_auth_config
from aqa_shared.db.models import Application
from aqa_shared.db.session import get_session_factory

PAYLOAD = {
    "name": "Verify Apps API Day12",
    "base_url": "https://juice-shop.herokuapp.com",
    "seed_urls": ["https://juice-shop.herokuapp.com/#/login"],
    "auth_config": {
        "type": "form",
        "login_url": "/#/login",
        "email_selector": "input[name=email]",
        "password_selector": "input[name=password]",
        "submit_selector": "#loginButton",
        "credentials_secret_ref": "JUICE_SHOP_TEST_USER",
    },
    "crawl_config": {"max_depth": 3, "max_pages": 20},
}


def main() -> int:
    print("verify:apps")
    client = TestClient(app)

    ssrf = client.post(
        "/api/v1/apps",
        json={
            "name": "SSRF Test",
            "base_url": "http://127.0.0.1:8080",
            "seed_urls": [],
        },
    )
    if ssrf.status_code != 400:
        print(f"FAIL SSRF: expected 400 got {ssrf.status_code} {ssrf.text}", file=sys.stderr)
        return 1
    if "private" not in ssrf.json().get("detail", "").lower():
        print(f"FAIL SSRF detail: {ssrf.json()}", file=sys.stderr)
        return 1
    print("OK SSRF blocked for http://127.0.0.1")

    create = client.post("/api/v1/apps", json=PAYLOAD)
    if create.status_code != 201:
        print(f"FAIL POST /apps: {create.status_code} {create.text}", file=sys.stderr)
        return 1

    body = create.json()
    app_id = body.get("app_id")
    auth = body.get("auth_config", {})

    if "credentials_secret_ref" in str(body):
        print("FAIL: response leaked auth secrets", file=sys.stderr)
        return 1
    if auth.get("configured") is not True or auth.get("type") != "form":
        print(f"FAIL: unexpected public auth_config: {auth}", file=sys.stderr)
        return 1
    print(f"OK POST /apps: app_id={app_id} auth_config sanitized")

    session = get_session_factory()()
    try:
        row = session.scalar(select(Application).where(Application.app_id == uuid.UUID(app_id)))
        if row is None:
            print("FAIL: application not found in DB", file=sys.stderr)
            return 1
        stored = row.auth_config if isinstance(row.auth_config, dict) else {}
        if not is_encrypted_auth_config(stored):
            print(f"FAIL: auth_config not encrypted in DB: {stored}", file=sys.stderr)
            return 1
        decrypted = decrypt_auth_config(stored)
        if decrypted.get("credentials_secret_ref") != "JUICE_SHOP_TEST_USER":
            print(f"FAIL: decrypt mismatch: {decrypted}", file=sys.stderr)
            return 1
        print("OK auth_config encrypted at rest and decryptable")
    finally:
        session.close()

    listing = client.get("/api/v1/apps")
    if listing.status_code != 200 or listing.json().get("total", 0) < 1:
        print(f"FAIL GET /apps: {listing.status_code}", file=sys.stderr)
        return 1
    print(f"OK GET /apps: total={listing.json()['total']}")

    detail = client.get(f"/api/v1/apps/{app_id}")
    if detail.status_code != 200 or detail.json()["name"] != PAYLOAD["name"]:
        print(f"FAIL GET /apps/{{id}}: {detail.status_code}", file=sys.stderr)
        return 1
    print("OK GET /apps/{id}")

    missing = client.get(f"/api/v1/apps/{uuid.uuid4()}")
    if missing.status_code != 404:
        print(f"FAIL GET missing app: expected 404 got {missing.status_code}", file=sys.stderr)
        return 1
    print("OK GET /apps/{id} 404 for unknown id")

    bad_seed = client.post(
        "/api/v1/apps",
        json={**PAYLOAD, "name": "Bad Seed", "seed_urls": ["https://evil.example.com/"]},
    )
    if bad_seed.status_code != 422:
        print(f"FAIL seed_urls validation: expected 422 got {bad_seed.status_code}", file=sys.stderr)
        return 1
    print("OK invalid seed_urls rejected")

    print("verify:apps OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
