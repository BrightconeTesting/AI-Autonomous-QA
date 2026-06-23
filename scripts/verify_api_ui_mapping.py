#!/usr/bin/env python3
"""Verify Phase B2 — API↔UI mapping correlation (Track 2)."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ["ENCRYPTION_KEY"] = os.getenv("ENCRYPTION_KEY") or ("0123456789abcdef" * 4)
os.environ.setdefault("DATABASE_URL", os.getenv("DATABASE_URL", ""))

from aqa_agents.discovery.appmap import load_appmap_for_application  # noqa: E402
from aqa_shared.discovery.api_ui_mapper import (  # noqa: E402
    build_api_ui_mappings,
    correlate_cic_interactions,
    correlate_form_endpoints,
    merge_api_ui_mappings,
)
from aqa_shared.db.models import ApiEndpoint, ApiUiMapping, Application, Form, Page  # noqa: E402
from aqa_shared.db.session import get_session_factory  # noqa: E402
from sqlalchemy import delete  # noqa: E402


def _verify_mapper_rules() -> bool:
    page_id = str(uuid.uuid4())
    endpoint_id = str(uuid.uuid4())
    form_id = str(uuid.uuid4())
    endpoint = {
        "endpoint_id": endpoint_id,
        "method": "POST",
        "path_pattern": "/api/users",
        "seen_on_page_ids": [page_id],
        "request_schema": {},
        "body_keys": ["email", "name"],
    }
    form = {
        "form_id": form_id,
        "page_id": page_id,
        "method": "post",
        "attributes": {"name": "user-form", "form_key": "form-1"},
    }
    elements = [
        {
            "element_id": str(uuid.uuid4()),
            "page_id": page_id,
            "text_content": "Email",
            "attributes": {"name": "email", "form_key": "form-1"},
        }
    ]

    form_mappings = correlate_form_endpoints(
        page_id=page_id,
        forms=[form],
        api_endpoints=[endpoint],
        elements=elements,
    )
    if not form_mappings:
        print("FAIL correlate_form_endpoints returned no mappings", file=sys.stderr)
        return False
    if form_mappings[0]["correlation_method"] != "form_body_field_match":
        print(f"FAIL expected form_body_field_match got {form_mappings[0]['correlation_method']}", file=sys.stderr)
        return False
    if float(form_mappings[0]["confidence"]) < 0.7:
        print(f"FAIL low form mapping confidence={form_mappings[0]['confidence']}", file=sys.stderr)
        return False

    cic_mappings = correlate_cic_interactions(
        page_id=page_id,
        interaction_events=[
            {
                "timestamp_ms": 1000.0,
                "interaction_key": "btn-save",
                "trigger_action": {"action_type": "click", "interaction_key": "btn-save"},
            }
        ],
        network_events=[
            {
                "timestamp_ms": 1300.0,
                "method": "POST",
                "path_pattern": "/api/users",
                "body_keys": ["email"],
            }
        ],
        forms=[form],
        elements=elements,
        endpoint_by_pattern={"POST /api/users": endpoint},
    )
    if not cic_mappings:
        print("FAIL correlate_cic_interactions returned no mappings", file=sys.stderr)
        return False
    if cic_mappings[0]["correlation_method"] not in {"cic_interaction_window", "form_body_field_match"}:
        print(f"FAIL unexpected cic method={cic_mappings[0]['correlation_method']}", file=sys.stderr)
        return False
    if float(cic_mappings[0]["confidence"]) < 0.7:
        print(f"FAIL low cic confidence={cic_mappings[0]['confidence']}", file=sys.stderr)
        return False

    merged = merge_api_ui_mappings(form_mappings, cic_mappings)
    if len(merged) < 1:
        print("FAIL merge_api_ui_mappings empty", file=sys.stderr)
        return False

    print("OK mapper rules (form_body_field_match, cic_interaction_window, merge)")
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
                name=f"verify-api-ui-{app_id.hex[:8]}",
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

        mappings = build_api_ui_mappings(
            pages=[{"page_id": str(page_id), "url": "https://example.com/app/users", "title": "Users"}],
            forms=[
                {
                    "form_id": str(form_id),
                    "page_id": str(page_id),
                    "method": "post",
                    "attributes": {"name": "create-user", "form_key": "create-user"},
                    "field_element_ids": [],
                }
            ],
            elements=[],
            api_endpoints=[
                {
                    "endpoint_id": str(endpoint_id),
                    "method": "POST",
                    "path_pattern": "/api/users",
                    "seen_on_page_ids": [str(page_id)],
                    "first_seen_page_id": str(page_id),
                    "source": "network",
                    "request_schema": {},
                }
            ],
        )
        if not mappings:
            print("FAIL build_api_ui_mappings returned no rows", file=sys.stderr)
            return False

        session.add(
            ApiUiMapping(
                app_id=app_id,
                api_endpoint_id=endpoint_id,
                page_id=page_id,
                form_id=form_id,
                trigger_action={"action": "submit"},
                confidence=float(mappings[0]["confidence"]),
                correlation_method=str(mappings[0]["correlation_method"]),
                review_required=bool(mappings[0].get("review_required")),
            )
        )
        session.flush()

        document = load_appmap_for_application(session, app_id)
        if document is None:
            print("FAIL load_appmap_for_application returned None", file=sys.stderr)
            return False
        api_ui_mappings = document.get("api_ui_mappings") or []
        if not api_ui_mappings:
            print("FAIL appmap missing api_ui_mappings", file=sys.stderr)
            return False
        if float(api_ui_mappings[0].get("confidence") or 0) < 0.4:
            print(f"FAIL mapping confidence below gate: {api_ui_mappings[0]}", file=sys.stderr)
            return False
        if (document.get("stats") or {}).get("api_ui_mapping_count", 0) < 1:
            print("FAIL stats.api_ui_mapping_count missing", file=sys.stderr)
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

    print("OK appmap integration (api_ui_mappings[], stats.api_ui_mapping_count)")
    return True


def main() -> int:
    print("verify:api-ui-mapping")
    checks = [_verify_mapper_rules, _verify_appmap_integration]
    for check in checks:
        if not check():
            return 1
    print("verify:api-ui-mapping OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
