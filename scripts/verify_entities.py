#!/usr/bin/env python3
"""Verify Phase C — data entity inference and flow module linkage."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import delete

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ["ENCRYPTION_KEY"] = os.getenv("ENCRYPTION_KEY") or ("0123456789abcdef" * 4)
os.environ.setdefault("DATABASE_URL", os.getenv("DATABASE_URL", ""))

from aqa_agents.discovery.appmap import load_appmap_for_application  # noqa: E402
from aqa_agents.discovery.entities import (  # noqa: E402
    build_entities_rule_pass,
    link_flows_to_modules,
)
from aqa_shared.db.models import ApiEndpoint, Application, Form, Page  # noqa: E402
from aqa_shared.db.session import get_session_factory  # noqa: E402


def _verify_rule_inference() -> bool:
    page_id = str(uuid.uuid4())
    form_id = str(uuid.uuid4())
    endpoint_id = str(uuid.uuid4())
    pages = [{"page_id": page_id, "url": "https://example.com/app/users", "title": "Create User"}]
    forms = [
        {
            "form_id": form_id,
            "page_id": page_id,
            "method": "post",
            "attributes": {"name": "create-user", "form_key": "create-user"},
            "field_element_ids": [],
        }
    ]
    elements = [
        {
            "element_id": str(uuid.uuid4()),
            "page_id": page_id,
            "tag_name": "input",
            "text_content": "Email",
            "attributes": {"name": "email"},
        }
    ]
    api_endpoints = [
        {
            "endpoint_id": endpoint_id,
            "method": "POST",
            "path": "/api/users",
            "path_pattern": "/api/users",
            "source": "network",
            "seen_on_page_ids": [page_id],
            "request_schema": {},
            "body_keys": ["email", "role"],
        }
    ]
    modules = [
        {
            "module_id": "users",
            "name": "Users",
            "parent_module_id": None,
            "pages": [page_id],
            "features": [],
        }
    ]

    entities = build_entities_rule_pass(
        pages=pages,
        elements=elements,
        forms=forms,
        api_endpoints=api_endpoints,
        modules=modules,
        api_ui_mappings=[],
    )
    if not entities:
        print("FAIL build_entities_rule_pass returned no entities", file=sys.stderr)
        return False

    user = next((entity for entity in entities if entity.get("entity_id") == "user"), None)
    if user is None:
        print(f"FAIL expected user entity, got {[e.get('entity_id') for e in entities]}", file=sys.stderr)
        return False
    if "email" not in (user.get("fields") or []):
        print(f"FAIL user fields missing email: {user.get('fields')}", file=sys.stderr)
        return False
    create = (user.get("crud_surfaces") or {}).get("create") or {}
    if endpoint_id not in [str(item) for item in (create.get("api_endpoint_ids") or [])]:
        print(f"FAIL create surface missing endpoint: {create}", file=sys.stderr)
        return False
    if float(user.get("confidence") or 0) < 0.6:
        print(f"FAIL entity confidence below gate: {user.get('confidence')}", file=sys.stderr)
        return False

    flows = link_flows_to_modules(
        [
            {
                "flow_id": str(uuid.uuid4()),
                "name": "Users flow",
                "steps": [{"action": "navigate", "page_id": page_id, "url": pages[0]["url"]}],
            }
        ],
        pages,
        modules,
    )
    if not flows or flows[0].get("module_id") != "users":
        print(f"FAIL flow module_id linkage: {flows}", file=sys.stderr)
        return False

    print("OK entity rule inference + flow module_id linkage")
    return True


def _verify_appmap_integration() -> bool:
    app_id = uuid.uuid4()
    page_id = uuid.uuid4()
    form_id = uuid.uuid4()
    endpoint_id = uuid.uuid4()

    session = get_session_factory()()
    try:
        session.add(
            Application(
                app_id=app_id,
                name=f"verify-entities-{app_id.hex[:8]}",
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
                form_id=form_id,
                app_id=app_id,
                page_id=page_id,
                method="post",
                attributes={"name": "create-user", "form_key": "create-user"},
                field_element_ids=[],
            )
        )
        session.add(
            ApiEndpoint(
                endpoint_id=endpoint_id,
                app_id=app_id,
                method="POST",
                path="/api/users",
                path_pattern="/api/users",
                source="network",
                first_seen_page_id=page_id,
                seen_page_ids=[str(page_id)],
            )
        )
        session.flush()

        document = load_appmap_for_application(session, app_id)
        if document is None:
            print("FAIL load_appmap_for_application returned None", file=sys.stderr)
            return False
        entities = document.get("data_entities") or []
        if not entities:
            print("FAIL appmap missing data_entities", file=sys.stderr)
            return False
        if (document.get("stats") or {}).get("entity_count", 0) < 1:
            print("FAIL stats.entity_count missing", file=sys.stderr)
            return False
        if int(document.get("schema_version") or 0) < 3:
            print(f"FAIL schema_version={document.get('schema_version')}", file=sys.stderr)
            return False
    except Exception:
        session.rollback()
        raise
    finally:
        try:
            session.execute(delete(Application).where(Application.app_id == app_id))
            session.commit()
        except Exception:
            session.rollback()
        session.close()

    print("OK appmap integration (data_entities[], stats.entity_count, schema_version>=3)")
    return True


def main() -> int:
    print("verify:entities")
    checks = [_verify_rule_inference, _verify_appmap_integration]
    for check in checks:
        if not check():
            return 1
    print("verify:entities OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
