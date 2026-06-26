#!/usr/bin/env python3
"""Verify Phase D — recommended_test_areas and TestDesign handoff."""

from __future__ import annotations

import json
import sys
import uuid

from aqa_agents.discovery.discovery_summary import build_discovery_summary  # noqa: E402
from aqa_agents.discovery.scoring import apply_scoring  # noqa: E402
from aqa_agents.discovery.test_areas import (  # noqa: E402
    attach_module_test_areas,
    build_test_areas_rule_pass,
)
from aqa_agents.test_design.gap_fill import compact_appmap_for_prompt  # noqa: E402
from aqa_agents.test_design.templates import generate_cases_from_recommended_areas  # noqa: E402


def _fixture() -> dict:
    page_id = str(uuid.uuid4())
    form_id = str(uuid.uuid4())
    element_id = str(uuid.uuid4())
    endpoint_id = str(uuid.uuid4())
    delete_element_id = str(uuid.uuid4())
    return {
        "page_id": page_id,
        "form_id": form_id,
        "element_id": element_id,
        "endpoint_id": endpoint_id,
        "delete_element_id": delete_element_id,
        "pages": [
            {
                "page_id": page_id,
                "url": "https://example.com/app/users",
                "title": "Users",
            }
        ],
        "elements": [
            {
                "element_id": element_id,
                "page_id": page_id,
                "semantic_selector": 'getByLabel("Email")',
                "text_content": "Email",
                "attributes": {"name": "email", "type": "email"},
            },
            {
                "element_id": delete_element_id,
                "page_id": page_id,
                "semantic_selector": 'getByRole("button", { name: "Delete user" })',
                "text_content": "Delete user",
                "role": "button",
                "tag_name": "button",
            },
        ],
        "modules": [
            {
                "module_id": "users",
                "name": "Users",
                "pages": [page_id],
                "flow_ids": [],
                "features": [],
            }
        ],
        "forms": [
            {
                "form_id": form_id,
                "page_id": page_id,
                "method": "post",
                "name": "create-user",
                "attributes": {"name": "create-user"},
                "field_element_ids": [element_id],
            }
        ],
        "api_endpoints": [
            {
                "endpoint_id": endpoint_id,
                "method": "POST",
                "path": "/api/users",
                "path_pattern": "/api/users",
                "seen_on_page_ids": [page_id],
            }
        ],
        "api_ui_mappings": [],
        "data_entities": [],
        "auth_intelligence": {
            "login_flow_id": str(uuid.uuid4()),
            "login_api_endpoint_id": str(uuid.uuid4()),
        },
        "test_data_catalog": [
            {
                "catalog_id": str(uuid.uuid4()),
                "target_type": "form",
                "target_id": form_id,
                "fields": [
                    {
                        "name": "email",
                        "suggested_safe_value": "qa-user@example.com",
                    }
                ],
            }
        ],
    }


def _verify_rule_pass() -> bool:
    fixture = _fixture()
    scored = apply_scoring(
        pages=fixture["pages"],
        elements=fixture["elements"],
        flows=[],
        modules=fixture["modules"],
        forms=fixture["forms"],
        api_endpoints=fixture["api_endpoints"],
        api_ui_mappings=fixture["api_ui_mappings"],
        data_entities=fixture["data_entities"],
    )
    areas = build_test_areas_rule_pass(
        pages=fixture["pages"],
        elements=fixture["elements"],
        forms=scored["forms"],
        api_endpoints=scored["api_endpoints"],
        api_ui_mappings=fixture["api_ui_mappings"],
        data_entities=fixture["data_entities"],
        flows=[],
        modules=scored["modules"],
        auth_intelligence=fixture["auth_intelligence"],
    )
    if not areas:
        print("FAIL build_test_areas_rule_pass returned no areas", file=sys.stderr)
        return False

    area_types = {str(area.get("area_type") or "") for area in areas}
    required = {"form_validation", "api_contract", "destructive_control", "auth_flow"}
    missing = required - area_types
    if missing:
        print(f"FAIL missing area types: {missing}", file=sys.stderr)
        return False

    for area in areas:
        if not area.get("area_id") or not area.get("priority_index"):
            print(f"FAIL area missing id/priority_index: {area}", file=sys.stderr)
            return False

    modules = attach_module_test_areas(scored["modules"], areas)
    users_module = next(item for item in modules if item.get("module_id") == "users")
    if not users_module.get("recommended_test_areas"):
        print("FAIL module missing recommended_test_areas slice", file=sys.stderr)
        return False

    print(f"OK rule pass produced {len(areas)} areas with module slices")
    return True


def _verify_test_design_handoff() -> bool:
    fixture = _fixture()
    scored = apply_scoring(
        pages=fixture["pages"],
        elements=fixture["elements"],
        flows=[],
        modules=fixture["modules"],
        forms=fixture["forms"],
        api_endpoints=fixture["api_endpoints"],
        api_ui_mappings=fixture["api_ui_mappings"],
        data_entities=fixture["data_entities"],
    )
    areas = build_test_areas_rule_pass(
        pages=fixture["pages"],
        elements=fixture["elements"],
        forms=scored["forms"],
        api_endpoints=scored["api_endpoints"],
        api_ui_mappings=fixture["api_ui_mappings"],
        data_entities=fixture["data_entities"],
        flows=[],
        modules=scored["modules"],
        auth_intelligence=fixture["auth_intelligence"],
    )
    appmap = {
        "pages": fixture["pages"],
        "elements": fixture["elements"],
        "flows": [],
        "forms": scored["forms"],
        "api_endpoints": scored["api_endpoints"],
        "api_ui_mappings": fixture["api_ui_mappings"],
        "test_data_catalog": fixture["test_data_catalog"],
        "recommended_test_areas": areas,
    }
    compact = json.loads(compact_appmap_for_prompt(appmap))
    if not compact.get("recommended_test_areas"):
        print("FAIL compact_appmap_for_prompt missing recommended_test_areas", file=sys.stderr)
        return False
    if not compact.get("test_data_catalog"):
        print("FAIL compact_appmap_for_prompt missing test_data_catalog", file=sys.stderr)
        return False

    cases = generate_cases_from_recommended_areas(appmap, max_tests=5, priorities=["critical", "high", "medium"])
    if not cases:
        print("FAIL generate_cases_from_recommended_areas returned no cases", file=sys.stderr)
        return False
    if not any("recommended_area_id" in case for case in cases):
        print("FAIL generated cases missing recommended_area_id", file=sys.stderr)
        return False

    summary = build_discovery_summary(appmap)
    tested_first = summary.get("what_should_be_tested_first") or []
    if not tested_first:
        print("FAIL discovery summary missing what_should_be_tested_first", file=sys.stderr)
        return False
    if tested_first[0] not in {str(area.get("area") or "") for area in areas}:
        print(
            f"FAIL discovery summary first item not from recommended areas: {tested_first[0]}",
            file=sys.stderr,
        )
        return False

    print(f"OK TestDesign handoff ({len(cases)} cases, summary={len(tested_first)} priorities)")
    return True


def main() -> int:
    print("verify:recommended-test-areas")
    ok = _verify_rule_pass() and _verify_test_design_handoff()
    if not ok:
        return 1
    print("verify:recommended-test-areas OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
