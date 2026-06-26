#!/usr/bin/env python3
"""Verify G2 — test data catalog inference."""

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
from aqa_shared.discovery.test_data_discovery import build_test_data_catalog  # noqa: E402
from aqa_shared.db.models import Application, Element, Form, Page  # noqa: E402
from aqa_shared.db.session import get_session_factory  # noqa: E402


def _verify_builder() -> bool:
    page_id = str(uuid.uuid4())
    form_id = str(uuid.uuid4())
    email_element_id = str(uuid.uuid4())
    elements = [
        {
            "element_id": email_element_id,
            "page_id": page_id,
            "tag_name": "input",
            "attributes": {
                "name": "email",
                "type": "email",
                "html5": {"type": "email", "required": True},
            },
        }
    ]
    forms = [
        {
            "form_id": form_id,
            "page_id": page_id,
            "field_element_ids": [email_element_id],
        }
    ]
    api_endpoints = [
        {
            "endpoint_id": str(uuid.uuid4()),
            "method": "POST",
            "path": "/api/users",
            "path_pattern": "/api/users",
            "body_keys": ["email", "role"],
            "request_schema": {},
        }
    ]
    data_entities = [
        {
            "entity_id": "user",
            "name": "User",
            "fields": ["email", "role"],
        }
    ]

    catalog = build_test_data_catalog(
        forms=forms,
        elements=elements,
        api_endpoints=api_endpoints,
        data_entities=data_entities,
        run_id="verify-run",
    )
    if len(catalog) < 3:
        print(f"FAIL catalog entries expected >=3, got {len(catalog)}: {catalog}", file=sys.stderr)
        return False

    form_entry = next((item for item in catalog if item.get("target_type") == "form"), None)
    if form_entry is None:
        print("FAIL missing form catalog entry", file=sys.stderr)
        return False
    email_field = next((field for field in form_entry.get("fields") or [] if field.get("name") == "email"), None)
    if email_field is None:
        print(f"FAIL form entry missing email field: {form_entry}", file=sys.stderr)
        return False
    if email_field.get("pii_class") != "email":
        print(f"FAIL email pii_class: {email_field}", file=sys.stderr)
        return False
    if not form_entry.get("never_use_live_pii"):
        print("FAIL never_use_live_pii must be true", file=sys.stderr)
        return False
    if "@example.com" not in str(email_field.get("suggested_safe_value") or ""):
        print(f"FAIL synthetic email value: {email_field}", file=sys.stderr)
        return False

    api_entry = next((item for item in catalog if item.get("target_type") == "api_endpoint"), None)
    if api_entry is None or len(api_entry.get("fields") or []) < 2:
        print(f"FAIL api_endpoint catalog entry: {api_entry}", file=sys.stderr)
        return False

    entity_entry = next((item for item in catalog if item.get("target_type") == "entity"), None)
    if entity_entry is None:
        print("FAIL entity catalog entry missing", file=sys.stderr)
        return False

    print("OK test data catalog builder (form, api_endpoint, entity, never_use_live_pii)")
    return True


def _verify_unfilled_form_fields() -> bool:
    """Forms without name attributes and fields not filled during crawl still produce test data."""
    page_id = str(uuid.uuid4())
    form_id = str(uuid.uuid4())
    search_id = str(uuid.uuid4())
    filled_id = str(uuid.uuid4())
    elements = [
        {
            "element_id": search_id,
            "page_id": page_id,
            "tag_name": "input",
            "role": "textbox",
            "semantic_selector": 'getByPlaceholder("Search manufacturer")',
            "attributes": {"type": "text"},
        },
        {
            "element_id": filled_id,
            "page_id": page_id,
            "tag_name": "input",
            "role": "textbox",
            "attributes": {
                "type": "email",
                "filled_during_crawl": True,
                "interaction_key": "fill|email",
            },
        },
    ]
    forms = [
        {
            "form_id": form_id,
            "page_id": page_id,
            "field_element_ids": [search_id, filled_id],
        }
    ]

    catalog = build_test_data_catalog(
        forms=forms,
        elements=elements,
        api_endpoints=[],
        run_id="verify-unfilled",
    )
    if len(catalog) != 1:
        print(f"FAIL expected one form catalog entry, got {catalog}", file=sys.stderr)
        return False

    entry = catalog[0]
    if entry.get("unfilled_field_count") != 1:
        print(f"FAIL unfilled_field_count expected 1, got {entry}", file=sys.stderr)
        return False

    search_field = next((field for field in entry["fields"] if field.get("display_name") == "Search manufacturer"), None)
    if search_field is None:
        search_field = next((field for field in entry["fields"] if field["name"] == "search_manufacturer"), None)
    if search_field is None:
        print(f"FAIL missing placeholder-derived field: {entry['fields']}", file=sys.stderr)
        return False
    if not search_field.get("needs_test_data"):
        print(f"FAIL unfilled field should need test data: {search_field}", file=sys.stderr)
        return False
    if not search_field.get("semantic_selector"):
        print(f"FAIL semantic_selector not preserved: {search_field}", file=sys.stderr)
        return False

    filled_field = next((field for field in entry["fields"] if field.get("name") == "field_email"), None)
    if filled_field is None:
        print(f"FAIL missing filled field marker: {entry['fields']}", file=sys.stderr)
        return False
    if filled_field.get("needs_test_data"):
        print(f"FAIL filled field should not need test data: {filled_field}", file=sys.stderr)
        return False

    print("OK unfilled form fields cataloged with placeholder names and fill status")
    return True


def _verify_label_display_names() -> bool:
    """Field labels should appear as display_name, not placeholder hints."""
    page_id = str(uuid.uuid4())
    form_id = str(uuid.uuid4())
    manufacturer_id = str(uuid.uuid4())
    channel_id = str(uuid.uuid4())
    elements = [
        {
            "element_id": manufacturer_id,
            "page_id": page_id,
            "tag_name": "input",
            "role": "textbox",
            "semantic_selector": 'getByLabel("Manufacturer")',
            "attributes": {
                "type": "text",
                "label": "MANUFACTURER *",
                "placeholder": "e.g. Pfizer",
                "required": "true",
                "html5": {"required": True},
            },
        },
        {
            "element_id": channel_id,
            "page_id": page_id,
            "tag_name": "select",
            "role": "combobox",
            "semantic_selector": 'getByLabel("Preferred Channel")',
            "attributes": {
                "label": "PREFERRED CHANNEL",
            },
        },
    ]
    catalog = build_test_data_catalog(
        forms=[{"form_id": form_id, "page_id": page_id, "field_element_ids": [manufacturer_id, channel_id]}],
        elements=elements,
        api_endpoints=[],
        run_id="verify-labels",
    )
    fields = catalog[0]["fields"]
    mfr = next(f for f in fields if f["element_id"] == manufacturer_id)
    if mfr.get("display_name") != "MANUFACTURER":
        print(f"FAIL manufacturer display_name: {mfr}", file=sys.stderr)
        return False
    if mfr.get("name") == "eg_pfizer":
        print(f"FAIL manufacturer should not use placeholder as key: {mfr}", file=sys.stderr)
        return False
    channel = next(f for f in fields if f["element_id"] == channel_id)
    if channel.get("display_name") != "PREFERRED CHANNEL":
        print(f"FAIL channel display_name: {channel}", file=sys.stderr)
        return False
    print("OK label-based display_name for form catalog fields")
    return True


def _verify_form_deduplication() -> bool:
    """Same field surface captured in baseline and interaction states merges to one catalog row."""
    page_id = str(uuid.uuid4())
    email_id = str(uuid.uuid4())
    elements = [
        {
            "element_id": email_id,
            "page_id": page_id,
            "tag_name": "input",
            "attributes": {"name": "email", "type": "email", "html5": {"type": "email"}},
        }
    ]
    baseline_form_id = str(uuid.uuid4())
    inquiry_form_id = str(uuid.uuid4())
    voice_form_id = str(uuid.uuid4())
    baseline_state_id = str(uuid.uuid4())
    inquiry_state_id = str(uuid.uuid4())
    voice_state_id = str(uuid.uuid4())
    forms = [
        {
            "form_id": baseline_form_id,
            "page_id": page_id,
            "state_id": baseline_state_id,
            "field_element_ids": [email_id],
            "name": "Form 1",
        },
        {
            "form_id": inquiry_form_id,
            "page_id": page_id,
            "state_id": inquiry_state_id,
            "field_element_ids": [email_id],
            "name": "Form 1",
        },
        {
            "form_id": voice_form_id,
            "page_id": page_id,
            "state_id": voice_state_id,
            "field_element_ids": [email_id],
            "name": "Form 1",
        },
    ]
    states = [
        {
            "state_id": baseline_state_id,
            "state_key": "baseline-key",
            "parent_state_key": None,
            "trigger_action": {},
        },
        {
            "state_id": inquiry_state_id,
            "state_key": "inquiry-key",
            "parent_state_key": "baseline-key",
            "trigger_action": {"text_content": "+ New Inquiry", "action_type": "click"},
        },
        {
            "state_id": voice_state_id,
            "state_key": "voice-key",
            "parent_state_key": "baseline-key",
            "trigger_action": {"text_content": "Fill with voice", "action_type": "click"},
        },
    ]

    catalog = build_test_data_catalog(
        forms=forms,
        elements=elements,
        api_endpoints=[],
        states=states,
        run_id="verify-dedupe",
    )
    form_entries = [item for item in catalog if item.get("target_type") == "form"]
    if len(form_entries) != 1:
        print(f"FAIL expected 1 merged form entry, got {len(form_entries)}: {form_entries}", file=sys.stderr)
        return False

    entry = form_entries[0]
    reachable = entry.get("reachable_via") or []
    if len(reachable) < 1:
        print(f"FAIL expected reachable_via aliases, got {entry}", file=sys.stderr)
        return False
    if entry.get("target_id") not in {inquiry_form_id, voice_form_id}:
        print(f"FAIL winner should prefer interaction state, got {entry}", file=sys.stderr)
        return False

    print("OK duplicate form surfaces merge into one catalog entry with reachable_via")
    return True


def _verify_appmap_integration() -> bool:
    app_id = uuid.uuid4()
    page_id = uuid.uuid4()
    form_id = uuid.uuid4()
    element_id = uuid.uuid4()

    session = get_session_factory()()
    try:
        session.add(
            Application(
                app_id=app_id,
                name=f"verify-test-data-{app_id.hex[:8]}",
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
        session.add(
            Element(
                element_id=element_id,
                page_id=page_id,
                tag_name="input",
                attributes={
                    "name": "email",
                    "type": "email",
                    "html5": {"type": "email", "required": True},
                },
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
        session.flush()

        document = load_appmap_for_application(session, app_id)
        if document is None:
            print("FAIL load_appmap_for_application returned None", file=sys.stderr)
            return False
        catalog = document.get("test_data_catalog") or []
        if not catalog:
            print("FAIL test_data_catalog empty", file=sys.stderr)
            return False
        if not all(item.get("never_use_live_pii") for item in catalog):
            print(f"FAIL never_use_live_pii not set on all entries: {catalog}", file=sys.stderr)
            return False
        count = (document.get("stats") or {}).get("test_data_catalog_count", 0)
        if count < 1:
            print("FAIL stats.test_data_catalog_count missing", file=sys.stderr)
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

    print("OK appmap integration (test_data_catalog, stats.test_data_catalog_count)")
    return True


def main() -> int:
    print("verify:test-data-catalog")
    checks = [
        _verify_builder,
        _verify_unfilled_form_fields,
        _verify_label_display_names,
        _verify_form_deduplication,
        _verify_appmap_integration,
    ]
    for check in checks:
        if not check():
            return 1
    print("verify:test-data-catalog OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
