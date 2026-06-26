#!/usr/bin/env python3
"""Verify F+ — extended scoring for forms, APIs, and entities."""

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
from aqa_agents.discovery.scoring import (  # noqa: E402
    apply_scoring,
    compute_priority_index,
    score_api_endpoint_risk,
    score_form_risk,
)
from aqa_shared.db.models import ApiEndpoint, Application, Element, Form, Page  # noqa: E402
from aqa_shared.db.session import get_session_factory  # noqa: E402


def _verify_unit_rules() -> bool:
    form_id = str(uuid.uuid4())
    element_id = str(uuid.uuid4())
    form = {
        "form_id": form_id,
        "page_id": str(uuid.uuid4()),
        "method": "post",
        "name": "create-user",
        "attributes": {"name": "create-user"},
        "field_element_ids": [element_id],
    }
    elements_by_id = {
        element_id: {
            "element_id": element_id,
            "semantic_selector": "//input",
            "text_content": "Email",
            "attributes": {"name": "email", "type": "email"},
        }
    }
    risk, factors = score_form_risk(form, elements_by_id=elements_by_id, api_ui_mappings=[])
    if risk < 25:
        print(f"FAIL form risk too low: {risk} {factors}", file=sys.stderr)
        return False
    if "unmapped_mutating_form" not in factors:
        print(f"FAIL expected unmapped_mutating_form factor: {factors}", file=sys.stderr)
        return False

    endpoint = {
        "endpoint_id": str(uuid.uuid4()),
        "method": "POST",
        "path": "/api/auth/login",
        "path_pattern": "/api/auth/login",
    }
    api_risk, api_factors = score_api_endpoint_risk(endpoint, api_ui_mappings=[])
    if api_risk < 35:
        print(f"FAIL api risk too low: {api_risk} {api_factors}", file=sys.stderr)
        return False

    priority = compute_priority_index(
        risk_score=70,
        business_criticality="high",
        testability_score=40,
        automation_complexity_score=30,
    )
    if priority < 50:
        print(f"FAIL priority_index too low: {priority}", file=sys.stderr)
        return False

    print("OK F+ scoring rules (form risk, api risk, priority_index)")
    return True


def _verify_apply_scoring_rollup() -> bool:
    page_id = str(uuid.uuid4())
    form_id = str(uuid.uuid4())
    endpoint_id = str(uuid.uuid4())
    element_id = str(uuid.uuid4())
    scored = apply_scoring(
        pages=[{"page_id": page_id, "url": "https://example.com/app/users", "title": "Users"}],
        elements=[
            {
                "element_id": element_id,
                "page_id": page_id,
                "semantic_selector": 'getByLabel("Email")',
                "text_content": "Email",
            }
        ],
        flows=[],
        modules=[
            {
                "module_id": "users",
                "name": "Users",
                "pages": [page_id],
                "flow_ids": [],
                "features": [],
            }
        ],
        forms=[
            {
                "form_id": form_id,
                "page_id": page_id,
                "method": "post",
                "attributes": {"name": "create-user"},
                "field_element_ids": [element_id],
            }
        ],
        api_endpoints=[
            {
                "endpoint_id": endpoint_id,
                "method": "POST",
                "path": "/api/users",
                "path_pattern": "/api/users",
                "seen_on_page_ids": [page_id],
            }
        ],
        api_ui_mappings=[],
        data_entities=[
            {
                "entity_id": "user",
                "name": "User",
                "fields": ["email"],
                "module_id": "users",
                "risk_score": 35,
                "crud_surfaces": {
                    "create": {"api_endpoint_ids": [endpoint_id], "form_ids": [form_id], "page_ids": [page_id]}
                },
            }
        ],
        api_dependency_graph={
            "nodes": [{"endpoint_id": endpoint_id}],
            "edges": [],
        },
    )
    form = scored["forms"][0]
    endpoint = scored["api_endpoints"][0]
    module = scored["modules"][0]
    entity = scored["data_entities"][0]
    summary = scored["scoring_summary"]

    if form.get("priority_index") is None:
        print(f"FAIL form missing priority_index: {form}", file=sys.stderr)
        return False
    if endpoint.get("risk_factors") is None:
        print(f"FAIL endpoint missing risk_factors: {endpoint}", file=sys.stderr)
        return False
    if module.get("risk_score", 0) < form.get("risk_score", 0):
        print(f"FAIL module risk should roll up form risk: module={module} form={form}", file=sys.stderr)
        return False
    if entity.get("priority_index") is None:
        print(f"FAIL entity missing priority_index: {entity}", file=sys.stderr)
        return False
    if summary.get("mutating_api_count", 0) < 1:
        print(f"FAIL scoring_summary mutating_api_count: {summary}", file=sys.stderr)
        return False

    print("OK apply_scoring F+ rollup (forms, apis, entities, modules, summary)")
    return True


def _verify_appmap_integration() -> bool:
    app_id = uuid.uuid4()
    page_id = uuid.uuid4()
    form_id = uuid.uuid4()
    element_id = uuid.uuid4()
    endpoint_id = uuid.uuid4()

    session = get_session_factory()()
    try:
        session.add(
            Application(
                app_id=app_id,
                name=f"verify-scoring-fplus-{app_id.hex[:8]}",
                base_url="https://example.com/app/",
            )
        )
        session.add(
            Page(
                page_id=page_id,
                app_id=app_id,
                url="https://example.com/app/users/new",
                title="Create User",
            )
        )
        session.flush()
        session.add(
            Element(
                element_id=element_id,
                page_id=page_id,
                tag_name="input",
                semantic_selector='getByLabel("Email")',
                text_content="Email",
                attributes={"name": "email", "type": "email"},
            )
        )
        session.add(
            Form(
                form_id=form_id,
                app_id=app_id,
                page_id=page_id,
                method="post",
                attributes={"name": "create-user"},
                field_element_ids=[str(element_id)],
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

        forms = document.get("forms") or []
        apis = document.get("api_endpoints") or []
        summary = document.get("scoring_summary") or {}
        if not forms or forms[0].get("risk_score") is None:
            print(f"FAIL scored forms missing: {forms}", file=sys.stderr)
            return False
        if not apis or not apis[0].get("risk_factors"):
            print(f"FAIL scored apis missing risk_factors: {apis}", file=sys.stderr)
            return False
        if summary.get("high_risk_form_count") is None:
            print(f"FAIL scoring_summary missing high_risk_form_count: {summary}", file=sys.stderr)
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

    print("OK appmap integration (scored forms/apis, scoring_summary inventory)")
    return True


def main() -> int:
    print("verify:scoring-phase-f+")
    checks = [_verify_unit_rules, _verify_apply_scoring_rollup, _verify_appmap_integration]
    for check in checks:
        if not check():
            return 1
    print("verify:scoring-phase-f+ OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
