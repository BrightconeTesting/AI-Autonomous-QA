#!/usr/bin/env python3
"""Verify discovery scoring layer (M2)."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ.setdefault("DATABASE_URL", "postgresql://aqa:aqa@localhost:5432/autonomous_qa")

from aqa_agents.discovery.appmap import build_and_persist_appmap  # noqa: E402
from aqa_agents.discovery.scoring import apply_scoring, score_element_testability  # noqa: E402
from aqa_shared.db.models import Application, Element, Page, PipelineRun, PipelineStage, PipelineStatus  # noqa: E402
from aqa_shared.db.session import get_session_factory  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aqa_api.main import app  # noqa: E402


def _verify_element_testability() -> bool:
    high = score_element_testability({"semantic_selector": 'getByRole("button", { name: "Save" })'})
    low = score_element_testability({"xpath_fallback": "//div[@id='12345']/button"})
    if high <= low:
        print(f"FAIL testability high={high} low={low}", file=sys.stderr)
        return False
    print(f"OK element testability: high={high} low={low}")
    return True


def _verify_apply_scoring() -> bool:
    pages = [
        {"page_id": "p1", "url": "https://example.com/app/login", "title": "Login"},
        {"page_id": "p2", "url": "https://example.com/app/dashboard", "title": "Dashboard"},
    ]
    elements = [
        {
            "page_id": "p1",
            "semantic_selector": 'getByLabel("Password")',
            "text_content": "Password",
            "role": "textbox",
        },
        {
            "page_id": "p2",
            "semantic_selector": 'getByRole("button", { name: "Delete user" })',
            "text_content": "Delete user",
            "role": "button",
        },
    ]
    flows = [
        {
            "flow_id": "f1",
            "name": "Login flow",
            "steps": [{"action": "navigate", "page_id": "p1", "url": pages[0]["url"]}],
        },
        {
            "flow_id": "f2",
            "name": "Delete user flow",
            "steps": [
                {"action": "navigate", "page_id": "p2", "url": pages[1]["url"]},
                {"action": "click", "text_content": "Delete user"},
            ],
        },
    ]
    modules = [
        {
            "module_id": "login",
            "name": "Login",
            "parent_module_id": None,
            "pages": ["p1"],
            "flow_ids": ["f1"],
            "features": [],
        },
        {
            "module_id": "dashboard",
            "name": "Dashboard",
            "parent_module_id": None,
            "pages": ["p2"],
            "flow_ids": ["f2"],
            "features": [],
        },
    ]
    scored = apply_scoring(
        pages=pages,
        elements=elements,
        flows=flows,
        modules=modules,
        states=[],
        navigation_graph=[],
        crawl_config={"max_pages": 50},
    )
    summary = scored["scoring_summary"]
    if summary["discovery_completeness_score"] <= 0:
        print("FAIL completeness score should be > 0", file=sys.stderr)
        return False
    dash = next(m for m in scored["modules"] if m["module_id"] == "dashboard")
    if dash.get("risk_score", 0) < 20:
        print(f"FAIL dashboard risk too low: {dash}", file=sys.stderr)
        return False
    if not summary.get("top_risk_modules"):
        print("FAIL missing top_risk_modules", file=sys.stderr)
        return False
    print(
        f"OK apply_scoring: completeness={summary['discovery_completeness_score']} "
        f"app_risk={summary['app_risk_score']}"
    )
    return True


def _verify_appmap_api_scoring() -> bool:
    session = get_session_factory()()
    app_id = uuid.uuid4()
    pipeline_run_id = uuid.uuid4()
    try:
        session.add(
            Application(
                app_id=app_id,
                name=f"verify-scoring-{app_id.hex[:8]}",
                base_url="https://example.com/app/",
                crawl_config={"max_pages": 20},
            )
        )
        page = Page(app_id=app_id, url="https://example.com/app/users/list", title="Users")
        session.add(page)
        session.flush()
        session.add(
            Element(
                page_id=page.page_id,
                tag_name="button",
                role="button",
                semantic_selector='getByRole("button", { name: "Delete" })',
                text_content="Delete",
            )
        )
        session.add(
            PipelineRun(
                id=pipeline_run_id,
                application_id=app_id,
                status=PipelineStatus.completed,
                current_stage=PipelineStage.discover,
            )
        )
        session.commit()

        build_and_persist_appmap(
            application_id=app_id,
            pipeline_run_id=pipeline_run_id,
            db=session,
            use_llm=False,
        )

        client = TestClient(app)
        resp = client.get(f"/api/v1/apps/{app_id}/appmap")
        if resp.status_code != 200:
            print(f"FAIL GET appmap {resp.status_code}", file=sys.stderr)
            return False
        body = resp.json()
        if body.get("discovery_completeness_score") is None:
            print("FAIL missing discovery_completeness_score", file=sys.stderr)
            return False
        if not body.get("scoring_summary"):
            print("FAIL missing scoring_summary", file=sys.stderr)
            return False
        if not body.get("modules") or body["modules"][0].get("risk_score") is None:
            print(f"FAIL module scores missing: {body.get('modules')}", file=sys.stderr)
            return False
        print(
            f"OK API scoring: completeness={body['discovery_completeness_score']} "
            f"modules={len(body['modules'])}"
        )
    finally:
        from aqa_shared.db.models import Artifact, Flow

        session.query(Artifact).filter(Artifact.pipeline_run_id == pipeline_run_id).delete()
        session.query(Flow).filter(Flow.app_id == app_id).delete()
        session.query(Element).filter(Element.page_id == page.page_id).delete()
        session.query(Page).filter(Page.app_id == app_id).delete()
        session.query(PipelineRun).filter(PipelineRun.id == pipeline_run_id).delete()
        session.query(Application).filter(Application.app_id == app_id).delete()
        session.commit()
        session.close()
    return True


def main() -> int:
    print("verify:scoring")
    checks = [_verify_element_testability, _verify_apply_scoring, _verify_appmap_api_scoring]
    for check in checks:
        if not check():
            return 1
    print("verify:scoring OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
