#!/usr/bin/env python3
"""Verify test case persistence, Gherkin export, and execute API — Phase 1."""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import select

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ["ENCRYPTION_KEY"] = os.getenv("ENCRYPTION_KEY") or ("0123456789abcdef" * 4)
os.environ.setdefault("DATABASE_URL", os.getenv("DATABASE_URL", ""))

from aqa_api.main import app  # noqa: E402
from aqa_celery.agent_runner import run_design, run_generate_scripts  # noqa: E402
from aqa_shared.db.models import (  # noqa: E402
    Application,
    Flow,
    FlowSource,
    Page,
    PageState,
    PipelineRun,
    TestCase,
    TestScript,
)
from aqa_shared.db.session import get_session_factory  # noqa: E402


def _cleanup(session, app_id: uuid.UUID) -> None:
    from aqa_shared.db.models import Element, Result, TestRun

    run_ids = [row.run_id for row in session.scalars(select(TestRun).where(TestRun.app_id == app_id)).all()]
    for run_id in run_ids:
        session.query(Result).filter(Result.run_id == run_id).delete()
    session.query(TestRun).filter(TestRun.app_id == app_id).delete()
    session.query(TestScript).filter(
        TestScript.testcase_id.in_(session.query(TestCase.testcase_id).filter(TestCase.app_id == app_id))
    ).delete(synchronize_session=False)
    session.query(TestCase).filter(TestCase.app_id == app_id).delete()
    session.query(PipelineRun).filter(PipelineRun.application_id == app_id).delete()
    session.query(Flow).filter(Flow.app_id == app_id).delete()
    session.query(Element).filter(
        Element.page_id.in_(session.query(Page.page_id).filter(Page.app_id == app_id))
    ).delete(synchronize_session=False)
    session.query(PageState).filter(
        PageState.page_id.in_(session.query(Page.page_id).filter(Page.app_id == app_id))
    ).delete(synchronize_session=False)
    session.query(Page).filter(Page.app_id == app_id).delete()
    session.query(Application).filter(Application.app_id == app_id).delete()
    session.commit()


def _seed_appmap(session, app_id: uuid.UUID) -> None:
    page = Page(app_id=app_id, url="https://example.com/app/home", title="Home")
    session.add(page)
    session.flush()
    session.add(
        PageState(page_id=page.page_id, state_key="baseline", fingerprint="fp1", interaction_depth=0)
    )
    session.add(
        Flow(
            app_id=app_id,
            name="Home navigation",
            sequence=[
                {
                    "action": "navigate",
                    "page_id": str(page.page_id),
                    "url": page.url,
                    "title": page.title,
                },
                {
                    "action": "click",
                    "role": "link",
                    "text_content": "Settings",
                    "semantic_selector": "getByRole('link', { name: 'Settings' })",
                },
            ],
            source=FlowSource.crawler,
        )
    )
    app_row = session.get(Application, app_id)
    assert app_row is not None
    app_row.last_crawl_at = datetime.utcnow()
    session.commit()


def main() -> int:
    print("verify:test-cases")
    client = TestClient(app)
    session = get_session_factory()()
    app_id = uuid.uuid4()

    try:
        session.add(
            Application(
                app_id=app_id,
                name="Verify Test Cases App",
                base_url="https://example.com/app/",
            )
        )
        session.commit()
        _seed_appmap(session, app_id)

        gen = client.post(
            f"/api/v1/apps/{app_id}/generate-tests",
            json={"force": True, "requireAppmapV2": False, "use_llm": False},
        )
        if gen.status_code != 202:
            print(f"FAIL generate-tests: {gen.status_code} {gen.text}", file=sys.stderr)
            return 1
        pipeline_run_id = gen.json()["pipeline_run_id"]
        payload = {
            "pipelineRunId": pipeline_run_id,
            "applicationId": str(app_id),
            "generateConfig": gen.json().get("config") or {"max_tests": 50, "priorities": ["critical", "high"]},
        }
        run_row = session.get(PipelineRun, uuid.UUID(pipeline_run_id))
        if run_row is not None:
            payload["generateConfig"] = dict(run_row.config or {})
        payload["generateConfig"]["use_llm"] = False

        run_design(payload)
        run_generate_scripts(payload)

        listed = client.get(f"/api/v1/apps/{app_id}/test-cases")
        if listed.status_code != 200:
            print(f"FAIL list test-cases: {listed.status_code}", file=sys.stderr)
            return 1
        items = listed.json().get("items") or []
        if not items:
            print("FAIL no test cases persisted", file=sys.stderr)
            return 1
        if not items[0].get("feature"):
            print(f"FAIL missing gherkin feature: {items[0]}", file=sys.stderr)
            return 1
        print(f"OK GET test-cases returned {len(items)} with Gherkin summary")

        export = client.get(f"/api/v1/apps/{app_id}/test-cases/export.feature")
        if export.status_code != 200 or "Feature:" not in export.text:
            print(f"FAIL export.feature: {export.status_code}", file=sys.stderr)
            return 1
        print("OK export.feature returns Gherkin")

        execute = client.post(f"/api/v1/apps/{app_id}/execute", json={"force": True})
        if execute.status_code != 202:
            print(f"FAIL execute: {execute.status_code} {execute.text}", file=sys.stderr)
            return 1
        print("OK POST execute returns 202")

        from unittest.mock import patch

        from aqa_api.schemas.apps import AuthConfigInput, CreateApplicationRequest, CredentialsInput

        inline_body = CreateApplicationRequest(
            name="Inline Creds App",
            base_url="https://example.com/app/",
            auth_config=AuthConfigInput(
                type="form",
                email_selector="input[name=email]",
                password_selector="input[name=password]",
                submit_selector="button[type=submit]",
                credentials=CredentialsInput(email="user@example.com", password="secret"),
            ),
        )
        with patch("aqa_api.services.applications.validate_application_urls"):
            from aqa_api.services import applications as app_service

            inline_app = app_service.create_application(session, inline_body)
            inline_id = inline_app.app_id
        from aqa_shared.crypto.auth_config import decrypt_auth_config

        decrypted = decrypt_auth_config(
            inline_app.auth_config if isinstance(inline_app.auth_config, dict) else {}
        )
        creds = decrypted.get("credentials") or {}
        if creds.get("email") != "user@example.com" or creds.get("password") != "secret":
            print(f"FAIL inline credentials not stored: {decrypted}", file=sys.stderr)
            return 1
        session.query(Application).filter(Application.app_id == inline_id).delete()
        session.commit()
        print("OK inline credentials stored encrypted")
    finally:
        _cleanup(session, app_id)
        session.close()

    print("verify:test-cases OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
