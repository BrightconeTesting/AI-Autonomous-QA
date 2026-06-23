#!/usr/bin/env python3
"""Verify OpenAPI import (Phase B)."""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi.testclient import TestClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ["ENCRYPTION_KEY"] = os.getenv("ENCRYPTION_KEY") or ("0123456789abcdef" * 4)
os.environ.setdefault("DATABASE_URL", os.getenv("DATABASE_URL", ""))

from aqa_agents.discovery.appmap import load_appmap_for_application  # noqa: E402
from aqa_api.main import app  # noqa: E402
from aqa_discovery.openapi_import import endpoints_from_openapi, validate_openapi_url  # noqa: E402
from aqa_shared.db.models import ApiEndpoint, Application, Page  # noqa: E402
from aqa_shared.db.session import get_session_factory  # noqa: E402
from aqa_shared.security.url_validator import UrlSecurityError  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "openapi_sample.json"


def _verify_parse_fixture() -> bool:
    document = __import__("json").loads(FIXTURE.read_text(encoding="utf-8"))
    endpoints = endpoints_from_openapi(document)
    methods = {(ep.method, ep.path_pattern) for ep in endpoints}
    expected = {("GET", "/api/users"), ("POST", "/api/users"), ("DELETE", "/api/users/{id}")}
    if methods != expected:
        print(f"FAIL openapi parse methods={methods}", file=sys.stderr)
        return False
    print(f"OK openapi parse: {len(endpoints)} endpoints")
    return True


def _verify_ssrf_guard() -> bool:
    try:
        validate_openapi_url(
            "https://evil.example/api/openapi.json",
            base_url="https://example.com/app/",
            allowed_domains=["example.com"],
        )
    except UrlSecurityError:
        print("OK openapi SSRF guard blocks foreign host")
        return True
    print("FAIL openapi SSRF guard did not block", file=sys.stderr)
    return False


def _cleanup(session, app_id: uuid.UUID) -> None:
    session.query(ApiEndpoint).filter(ApiEndpoint.app_id == app_id).delete()
    session.query(Page).filter(Page.app_id == app_id).delete()
    session.query(Application).filter(Application.app_id == app_id).delete()
    session.commit()


def _verify_appmap_api() -> bool:
    client = TestClient(app)
    session_factory = get_session_factory()
    app_id = uuid.uuid4()

    with session_factory() as session:
        page = Page(app_id=app_id, url="https://example.com/app/dashboard", title="Dashboard")
        session.add(
            Application(
                app_id=app_id,
                name="API endpoint verify app",
                base_url="https://example.com/app/",
                crawl_config={"capture_network": True},
                last_crawl_at=datetime.utcnow(),
            )
        )
        session.add(page)
        session.flush()
        session.add(
            ApiEndpoint(
                app_id=app_id,
                method="POST",
                path="/api/users",
                path_pattern="/api/users",
                source="openapi",
                request_schema={"type": "object"},
                response_schema={"201": {"description": "created"}},
                first_seen_page_id=page.page_id,
                seen_page_ids=[str(page.page_id)],
                seen_count=1,
            )
        )
        session.commit()

    try:
        raw = load_appmap_for_application(session_factory(), app_id)
        if raw is None or len(raw.get("api_endpoints") or []) != 1:
            print(f"FAIL appmap api_endpoints={raw.get('api_endpoints') if raw else None}", file=sys.stderr)
            return False
        response = client.get(f"/api/v1/apps/{app_id}/appmap")
        payload = response.json()
        if len(payload.get("api_endpoints") or []) != 1:
            print(f"FAIL API api_endpoints={payload.get('api_endpoints')}", file=sys.stderr)
            return False
        if payload.get("stats", {}).get("api_endpoint_count") != 1:
            print("FAIL api_endpoint_count missing", file=sys.stderr)
            return False
        print("OK AppMap api_endpoints exposed via API")
        return True
    finally:
        with session_factory() as session:
            _cleanup(session, app_id)


def main() -> int:
    print("verify:openapi-import")
    ok = _verify_parse_fixture() and _verify_ssrf_guard() and _verify_appmap_api()
    if not ok:
        return 1
    print("verify:openapi-import OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
