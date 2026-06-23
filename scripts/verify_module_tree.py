#!/usr/bin/env python3
"""Verify module tree rule pass + AppMap v3 modules (M1)."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ.setdefault("DATABASE_URL", "postgresql://aqa:aqa@localhost:5432/autonomous_qa")

from aqa_agents.discovery.appmap import build_and_persist_appmap, build_appmap_document  # noqa: E402
from aqa_agents.discovery.module_tree import (  # noqa: E402
    build_modules_rule_pass,
    build_navigation_graph,
    validate_llm_modules,
)
from aqa_shared.db.models import Application, Page, PipelineRun, PipelineStage, PipelineStatus  # noqa: E402
from aqa_shared.db.session import get_session_factory  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aqa_api.main import app  # noqa: E402


def _verify_rule_modules() -> bool:
    pages = [
        {"page_id": "p1", "url": "https://example.com/app/dashboard", "title": "Dashboard"},
        {"page_id": "p2", "url": "https://example.com/app/users/list", "title": "Users"},
        {"page_id": "p3", "url": "https://example.com/app/users/create", "title": "Create User"},
    ]
    flows = [
        {
            "flow_id": "f1",
            "name": "Users flow",
            "module": "users",
            "steps": [{"action": "navigate", "page_id": "p2", "url": pages[1]["url"]}],
        }
    ]
    discoveries = [
        {
            "source_page_id": "p1",
            "url": "https://example.com/app/users/list",
            "discovered_via": "interaction",
            "trigger_action": {"text_content": "Users", "action_type": "click"},
        }
    ]
    modules, nav = build_modules_rule_pass(
        pages=pages,
        flows=flows,
        elements=[],
        discoveries=discoveries,
    )
    if len(modules) < 2:
        print(f"FAIL expected >=2 modules, got {len(modules)}", file=sys.stderr)
        return False
    module_ids = {m["module_id"] for m in modules}
    if "app" not in module_ids or "users" not in module_ids:
        print(f"FAIL module ids: {module_ids}", file=sys.stderr)
        return False
    app_mod = next(m for m in modules if m["module_id"] == "app")
    if "p1" not in app_mod["pages"]:
        print(f"FAIL app module pages (dashboard): {app_mod['pages']}", file=sys.stderr)
        return False
    users = next(m for m in modules if m["module_id"] == "users")
    if "p2" not in users["pages"] or "p3" not in users["pages"]:
        print(f"FAIL users pages: {users['pages']}", file=sys.stderr)
        return False
    if not nav:
        print("FAIL expected navigation_graph edges", file=sys.stderr)
        return False
    print(f"OK rule modules: {len(modules)} modules, {len(nav)} nav edges")
    return True


def _verify_llm_grounding() -> bool:
    pages = [{"page_id": "p1", "url": "https://example.com/app/home", "title": "Home"}]
    flows = [{"flow_id": "f1", "name": "Home flow", "module": "home", "steps": []}]
    rule_modules, _ = build_modules_rule_pass(pages=pages, flows=flows, elements=[], discoveries=[])
    bad = validate_llm_modules(
        [{"module_id": "home", "name": "Renamed", "pages": ["missing"], "features": []}],
        rule_modules=rule_modules,
        pages=pages,
        flows=flows,
    )
    if bad[0]["pages"] != ["p1"]:
        print(f"FAIL grounding fallback pages: {bad[0]['pages']}", file=sys.stderr)
        return False
    print("OK LLM module grounding rejects invented page ids")
    return True


def _verify_appmap_v3_persist() -> bool:
    session = get_session_factory()()
    app_id = uuid.uuid4()
    pipeline_run_id = uuid.uuid4()
    try:
        session.add(
            Application(
                app_id=app_id,
                name=f"verify-m1-{app_id.hex[:8]}",
                base_url="https://example.com/app/",
            )
        )
        session.add(
            Page(
                app_id=app_id,
                url="https://example.com/app/dashboard",
                title="Dashboard",
            )
        )
        session.add(
            Page(
                app_id=app_id,
                url="https://example.com/app/settings",
                title="Settings",
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

        result = build_and_persist_appmap(
            application_id=app_id,
            pipeline_run_id=pipeline_run_id,
            db=session,
            use_llm=False,
        )
        artifact = Path(result.appmap_path)
        if not artifact.is_file():
            print(f"FAIL missing artifact {artifact}", file=sys.stderr)
            return False
        import json

        saved = json.loads(artifact.read_text(encoding="utf-8"))
        if saved.get("schema_version") != 3:
            print(f"FAIL artifact schema_version={saved.get('schema_version')}", file=sys.stderr)
            return False
        if len(saved.get("modules") or []) < 1:
            print("FAIL artifact modules empty", file=sys.stderr)
            return False

        client = TestClient(app)
        resp = client.get(f"/api/v1/apps/{app_id}/appmap")
        if resp.status_code != 200:
            print(f"FAIL GET appmap status={resp.status_code}", file=sys.stderr)
            return False
        body = resp.json()
        if body.get("schema_version") != 3:
            print(f"FAIL API schema_version={body.get('schema_version')}", file=sys.stderr)
            return False
        if len(body.get("modules") or []) < 1:
            print("FAIL API modules empty", file=sys.stderr)
            return False
        if body["stats"].get("module_count", 0) < 1:
            print(f"FAIL module_count={body['stats']}", file=sys.stderr)
            return False
        print(
            f"OK AppMap v3 API: modules={len(body['modules'])} "
            f"schema_version={body['schema_version']}"
        )
    finally:
        from aqa_shared.db.models import Artifact, Element, Flow

        session.query(Artifact).filter(Artifact.pipeline_run_id == pipeline_run_id).delete()
        session.query(Flow).filter(Flow.app_id == app_id).delete()
        session.query(Element).filter(
            Element.page_id.in_(session.query(Page.page_id).filter(Page.app_id == app_id))
        ).delete(synchronize_session=False)
        session.query(Page).filter(Page.app_id == app_id).delete()
        session.query(PipelineRun).filter(PipelineRun.id == pipeline_run_id).delete()
        session.query(Application).filter(Application.app_id == app_id).delete()
        session.commit()
        session.close()
    return True


def main() -> int:
    print("verify:module-tree")
    checks = [_verify_rule_modules, _verify_llm_grounding, _verify_appmap_v3_persist]
    for check in checks:
        if not check():
            return 1
    print("verify:module-tree OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
