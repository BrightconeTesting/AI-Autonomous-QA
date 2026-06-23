#!/usr/bin/env python3
"""Verify discovery summary API and builder (M3)."""

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

from aqa_agents.discovery.discovery_summary import build_discovery_summary  # noqa: E402
from aqa_api.main import app  # noqa: E402
from aqa_shared.db.models import (  # noqa: E402
    Application,
    Element,
    Flow,
    FlowSource,
    Page,
    PageState,
    PipelineRun,
    PipelineStage,
    PipelineStatus,
)
from aqa_shared.db.session import get_session_factory  # noqa: E402


def _cleanup(session, app_id: uuid.UUID) -> None:
    from aqa_shared.db.models import StateTransition, TestCase

    session.query(TestCase).filter(TestCase.app_id == app_id).delete()
    session.query(PipelineRun).filter(PipelineRun.application_id == app_id).delete()
    session.query(StateTransition).filter(StateTransition.app_id == app_id).delete()
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


def _verify_builder() -> bool:
    appmap = {
        "application_id": str(uuid.uuid4()),
        "schema_version": 3,
        "pages": [
            {"page_id": "p1", "url": "https://example.com/app/dashboard", "title": "Dashboard"},
            {"page_id": "p2", "url": "https://example.com/app/users", "title": "Users"},
        ],
        "elements": [
            {
                "page_id": "p2",
                "tag_name": "button",
                "role": "button",
                "text_content": "Delete user",
            },
            {
                "page_id": "p2",
                "tag_name": "input",
                "role": "textbox",
                "text_content": "Email",
            },
        ],
        "flows": [
            {
                "flow_id": "f1",
                "name": "Manage users",
                "risk_score": 70,
                "risk_factors": ["mutating_action"],
            }
        ],
        "modules": [
            {
                "module_id": "users",
                "name": "Users",
                "parent_module_id": None,
                "pages": ["p2"],
                "flow_ids": ["f1"],
                "features": [{"name": "Create User"}],
                "risk_score": 70,
                "risk_factors": ["mutating_action"],
            }
        ],
        "scoring_summary": {
            "app_risk_score": 70,
            "discovery_completeness_score": 55,
            "top_risk_modules": [
                {
                    "module_id": "users",
                    "name": "Users",
                    "risk_score": 70,
                    "top_factor": "mutating_action",
                }
            ],
            "recommendations": ["Enable cic_mode:full for SPA nav discovery"],
        },
        "discovery_completeness_score": 55,
        "recommendations": ["Enable cic_mode:full for SPA nav discovery"],
    }
    summary = build_discovery_summary(appmap)
    if summary["counts"]["pages"] != 2:
        print(f"FAIL builder pages={summary['counts']['pages']}", file=sys.stderr)
        return False
    if "Dashboard" not in summary["what_pages_exist"]:
        print("FAIL builder missing Dashboard page", file=sys.stderr)
        return False
    if not summary["what_should_be_tested_first"]:
        print("FAIL builder empty test priorities", file=sys.stderr)
        return False
    if not summary["top_risk_areas"]:
        print("FAIL builder empty top_risk_areas", file=sys.stderr)
        return False
    if not summary["module_tree"]:
        print("FAIL builder empty module_tree", file=sys.stderr)
        return False
    print("OK discovery summary builder")
    return True


def _verify_api() -> bool:
    client = TestClient(app)
    session_factory = get_session_factory()
    app_id = uuid.uuid4()

    with session_factory() as session:
        session.add(
            Application(
                app_id=app_id,
                name="Summary verify app",
                base_url="https://example.com/app/",
                seed_urls=["https://example.com/app/"],
                crawl_config={"enable_cic": True},
                last_crawl_at=datetime.utcnow(),
            )
        )
        page = Page(app_id=app_id, url="https://example.com/app/home", title="Home")
        session.add(page)
        session.flush()
        session.add(
            PageState(page_id=page.page_id, state_key="baseline", fingerprint="fp1", interaction_depth=0)
        )
        session.add(
            Element(
                page_id=page.page_id,
                tag_name="button",
                role="button",
                text_content="Save",
                semantic_selector='getByRole("button", { name: "Save" })',
            )
        )
        session.add(
            Flow(
                app_id=app_id,
                name="Home flow",
                sequence=[{"action": "navigate", "page_id": str(page.page_id), "url": page.url}],
                source=FlowSource.crawler,
            )
        )
        session.add(
            PipelineRun(
                id=uuid.uuid4(),
                application_id=app_id,
                status=PipelineStatus.completed,
                current_stage=PipelineStage.discover,
                config={},
                started_at=datetime.utcnow(),
                ended_at=datetime.utcnow(),
            )
        )
        session.commit()

    try:
        response = client.get(f"/api/v1/apps/{app_id}/discovery-summary")
        if response.status_code != 200:
            print(f"FAIL discovery-summary status={response.status_code} body={response.text}", file=sys.stderr)
            return False
        payload = response.json()
        if payload["counts"]["pages"] < 1:
            print("FAIL discovery-summary missing pages", file=sys.stderr)
            return False
        if payload["schema_version"] < 1:
            print(f"FAIL discovery-summary schema_version={payload['schema_version']}", file=sys.stderr)
            return False
        if "Home" not in payload["what_pages_exist"]:
            print(f"FAIL discovery-summary pages={payload['what_pages_exist']}", file=sys.stderr)
            return False
        print(
            "OK discovery-summary API "
            f"pages={payload['counts']['pages']} modules={payload['counts']['modules']} "
            f"completeness={payload['discovery_completeness_score']}"
        )
        return True
    finally:
        with session_factory() as session:
            _cleanup(session, app_id)


def main() -> int:
    print("verify:discovery-summary")
    ok = _verify_builder() and _verify_api()
    if not ok:
        return 1
    print("verify:discovery-summary OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
