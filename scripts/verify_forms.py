#!/usr/bin/env python3
"""Verify Phase A — forms, testability enrichment, button intent (Track 2)."""

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
from aqa_discovery.forms import link_elements_to_forms  # noqa: E402
from aqa_discovery.types import ElementSnapshot, FormSnapshot  # noqa: E402
from aqa_shared.db.models import Application, Element, Form, Page  # noqa: E402
from aqa_shared.db.session import get_session_factory  # noqa: E402
from aqa_shared.testability.enrichment import enrich_element_attributes  # noqa: E402


def _verify_testability_enrichment() -> bool:
    attrs = enrich_element_attributes(
        tag_name="button",
        role="button",
        text_content="Delete user",
        semantic_selector='getByRole("button", { name: "Delete user" })',
        xpath_fallback='//*[@id="delete-btn"]',
        attributes={"type": "button"},
        page_url="https://example.com/app/users",
        allowed_domains=["example.com"],
    )
    if attrs.get("testability_tier") != "action":
        print(f"FAIL testability tier={attrs.get('testability_tier')}", file=sys.stderr)
        return False
    if attrs.get("button_intent") != "delete":
        print(f"FAIL button_intent={attrs.get('button_intent')}", file=sys.stderr)
        return False
    if not attrs.get("testability_score"):
        print("FAIL missing testability_score", file=sys.stderr)
        return False

    link_attrs = enrich_element_attributes(
        tag_name="a",
        role="link",
        text_content="Docs",
        semantic_selector='getByRole("link", { name: "Docs" })',
        xpath_fallback=None,
        attributes={"href": "https://external.io/docs"},
        page_url="https://example.com/app/home",
        allowed_domains=["example.com"],
    )
    if link_attrs.get("link_scope") != "external":
        print(f"FAIL link_scope={link_attrs.get('link_scope')}", file=sys.stderr)
        return False

    field_attrs = enrich_element_attributes(
        tag_name="input",
        role="textbox",
        text_content="Email",
        semantic_selector='getByLabel("Email")',
        xpath_fallback='//input[@name="email"]',
        attributes={"type": "email", "required": "true", "pattern": ".+@.+"},
        page_url="https://example.com/app/register",
        allowed_domains=["example.com"],
    )
    html5 = field_attrs.get("html5") or {}
    if not html5.get("required") or html5.get("type") != "email":
        print(f"FAIL html5={html5}", file=sys.stderr)
        return False

    print("OK testability enrichment (tier, intent, link_scope, html5)")
    return True


def _verify_form_linking() -> bool:
    elements = [
        ElementSnapshot(
            tag_name="input",
            role="textbox",
            text_content="Email",
            xpath_fallback="/html/body/form/input[1]",
            attributes={},
        ),
        ElementSnapshot(
            tag_name="button",
            role="button",
            text_content="Save",
            xpath_fallback="/html/body/form/button[1]",
            attributes={},
        ),
    ]
    forms = [
        FormSnapshot(
            form_key="register-form",
            name="Register",
            method="post",
            field_xpaths=["/html/body/form/input[1]"],
        )
    ]
    link_elements_to_forms(elements, forms)
    if elements[0].attributes.get("form_key") != "register-form":
        print("FAIL form_key not linked to field element", file=sys.stderr)
        return False
    if elements[1].attributes.get("form_key"):
        print("FAIL unrelated button incorrectly linked", file=sys.stderr)
        return False
    print("OK form field linking")
    return True


def _cleanup(session, app_id: uuid.UUID) -> None:
    from aqa_shared.db.models import Flow, PipelineRun, TestCase

    session.query(TestCase).filter(TestCase.app_id == app_id).delete()
    session.query(PipelineRun).filter(PipelineRun.application_id == app_id).delete()
    session.query(Form).filter(Form.app_id == app_id).delete()
    session.query(Element).filter(
        Element.page_id.in_(session.query(Page.page_id).filter(Page.app_id == app_id))
    ).delete(synchronize_session=False)
    session.query(Page).filter(Page.app_id == app_id).delete()
    session.query(Application).filter(Application.app_id == app_id).delete()
    session.commit()


def _verify_appmap_forms_api() -> bool:
    client = TestClient(app)
    session_factory = get_session_factory()
    app_id = uuid.uuid4()

    with session_factory() as session:
        session.add(
            Application(
                app_id=app_id,
                name="Forms verify app",
                base_url="https://example.com/app/",
                crawl_config={"enable_cic": True},
                last_crawl_at=datetime.utcnow(),
            )
        )
        page = Page(app_id=app_id, url="https://example.com/app/register", title="Register")
        session.add(page)
        session.flush()
        email_field = Element(
            page_id=page.page_id,
            tag_name="input",
            role="textbox",
            text_content="Email",
            semantic_selector='getByLabel("Email")',
            xpath_fallback="/html/body/form/input[1]",
            attributes={
                "element_kind": "input",
                "testability_tier": "action",
                "testability_score": 75,
                "html5": {"type": "email", "required": True},
            },
        )
        session.add(email_field)
        session.flush()
        session.add(
            Form(
                app_id=app_id,
                page_id=page.page_id,
                action="/api/register",
                method="post",
                attributes={"form_key": "register-form", "name": "Register"},
                field_element_ids=[str(email_field.element_id)],
            )
        )
        session.commit()

    try:
        raw = load_appmap_for_application(session_factory(), app_id)
        if raw is None:
            print("FAIL load_appmap returned None", file=sys.stderr)
            return False
        forms = raw.get("forms") or []
        if len(forms) != 1:
            print(f"FAIL expected 1 form, got {len(forms)}", file=sys.stderr)
            return False
        if forms[0].get("method") != "post":
            print(f"FAIL form method={forms[0].get('method')}", file=sys.stderr)
            return False

        response = client.get(f"/api/v1/apps/{app_id}/appmap")
        if response.status_code != 200:
            print(f"FAIL appmap status={response.status_code}", file=sys.stderr)
            return False
        payload = response.json()
        if len(payload.get("forms") or []) != 1:
            print(f"FAIL API forms={payload.get('forms')}", file=sys.stderr)
            return False
        if payload.get("stats", {}).get("form_count") != 1:
            print(f"FAIL form_count={payload.get('stats', {}).get('form_count')}", file=sys.stderr)
            return False

        elements = payload.get("elements") or []
        enriched = [el for el in elements if el.get("attributes", {}).get("testability_tier")]
        if not enriched:
            print("FAIL no enriched elements in appmap", file=sys.stderr)
            return False

        print("OK AppMap forms persisted and exposed via API")
        return True
    finally:
        with session_factory() as session:
            _cleanup(session, app_id)


def main() -> int:
    print("verify:forms")
    ok = _verify_testability_enrichment() and _verify_form_linking() and _verify_appmap_forms_api()
    if not ok:
        return 1
    print("verify:forms OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
