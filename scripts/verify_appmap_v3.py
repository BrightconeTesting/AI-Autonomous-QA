#!/usr/bin/env python3
"""Verify AppMap v3 Track 2 fields present after Phase C."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import delete

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ["ENCRYPTION_KEY"] = os.getenv("ENCRYPTION_KEY") or ("0123456789abcdef" * 4)
os.environ.setdefault("DATABASE_URL", os.getenv("DATABASE_URL", ""))

from aqa_api.main import app  # noqa: E402
from aqa_shared.db.models import ApiEndpoint, Application, Form, Page  # noqa: E402
from aqa_shared.db.session import get_session_factory  # noqa: E402


def main() -> int:
    print("verify:appmap-v3")
    app_id = uuid.uuid4()
    page_id = uuid.uuid4()
    session = get_session_factory()()
    try:
        session.add(
            Application(
                app_id=app_id,
                name=f"verify-appmap-v3-{app_id.hex[:8]}",
                base_url="https://example.com/app/",
            )
        )
        session.add(
            Page(
                page_id=page_id,
                app_id=app_id,
                url="https://example.com/app/users",
                title="Users",
            )
        )
        session.flush()
        session.add(
            Form(
                app_id=app_id,
                page_id=page_id,
                method="post",
                attributes={"name": "create-user"},
                field_element_ids=[],
            )
        )
        session.add(
            ApiEndpoint(
                app_id=app_id,
                method="POST",
                path="/api/users",
                path_pattern="/api/users",
                source="network",
                first_seen_page_id=page_id,
                seen_page_ids=[str(page_id)],
            )
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    client = TestClient(app)
    response = client.get(f"/api/v1/apps/{app_id}/appmap")
    try:
        session = get_session_factory()()
        session.execute(delete(Application).where(Application.app_id == app_id))
        session.commit()
        session.close()
    except Exception:
        pass

    if response.status_code != 200:
        print(f"FAIL GET appmap status={response.status_code}", file=sys.stderr)
        return 1
    payload = response.json()
    if int(payload.get("schema_version") or 0) < 3:
        print(f"FAIL schema_version={payload.get('schema_version')}", file=sys.stderr)
        return 1
    required = ("modules", "forms", "api_endpoints", "data_entities", "scoring_summary")
    for key in required:
        if key not in payload:
            print(f"FAIL missing appmap key: {key}", file=sys.stderr)
            return 1
    if not payload.get("data_entities"):
        print("FAIL data_entities empty", file=sys.stderr)
        return 1
    stats = payload.get("stats") or {}
    if int(stats.get("entity_count") or 0) < 1:
        print(f"FAIL stats.entity_count={stats.get('entity_count')}", file=sys.stderr)
        return 1

    print("OK AppMap v3 API exposes modules, forms, apis, data_entities, scoring_summary")
    print("verify:appmap-v3 OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
