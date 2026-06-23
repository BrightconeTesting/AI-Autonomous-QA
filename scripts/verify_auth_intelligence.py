#!/usr/bin/env python3
"""Verify G2 — authentication intelligence and persona visibility."""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import delete

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ["ENCRYPTION_KEY"] = os.getenv("ENCRYPTION_KEY") or ("0123456789abcdef" * 4)
os.environ.setdefault("DATABASE_URL", os.getenv("DATABASE_URL", ""))

from aqa_agents.discovery.appmap import artifact_storage_root, load_appmap_for_application  # noqa: E402
from aqa_shared.discovery.auth_intelligence import build_auth_intelligence  # noqa: E402
from aqa_shared.discovery.persona_merge import build_persona_visibility_artifact, build_visibility_matrix  # noqa: E402
from aqa_shared.db.models import (  # noqa: E402
    Application,
    Artifact,
    ArtifactType,
    Element,
    Form,
    Page,
    PipelineRun,
    PipelineStage,
    PipelineStatus,
)
from aqa_shared.db.session import get_session_factory  # noqa: E402


def _verify_builder() -> bool:
    page_id = str(uuid.uuid4())
    form_id = str(uuid.uuid4())
    endpoint_id = str(uuid.uuid4())
    flow_id = str(uuid.uuid4())
    pages = [
        {
            "page_id": page_id,
            "url": "https://example.com/app/login",
            "title": "Login",
        }
    ]
    elements = [
        {
            "element_id": str(uuid.uuid4()),
            "page_id": page_id,
            "tag_name": "input",
            "attributes": {"name": "username", "type": "text"},
        },
        {
            "element_id": str(uuid.uuid4()),
            "page_id": page_id,
            "tag_name": "input",
            "attributes": {"name": "password", "type": "password"},
        },
    ]
    forms = [
        {
            "form_id": form_id,
            "page_id": page_id,
            "attributes": {"name": "login"},
            "field_element_ids": [elements[0]["element_id"], elements[1]["element_id"]],
        }
    ]
    api_endpoints = [
        {
            "endpoint_id": endpoint_id,
            "method": "POST",
            "path": "/api/auth/login",
            "path_pattern": "/api/auth/login",
            "request_headers": {"Authorization": "Bearer"},
        }
    ]
    flows = [
        {
            "flow_id": flow_id,
            "name": "Login flow",
            "steps": [{"action": "navigate", "page_id": page_id}],
        }
    ]
    modules = [
        {
            "module_id": "auth",
            "name": "Auth",
            "pages": [page_id],
            "features": [],
        },
        {
            "module_id": "admin",
            "name": "Admin",
            "pages": [],
            "features": [],
        },
    ]
    persona_visibility = build_persona_visibility_artifact(
        persona_results=[
            {
                "persona_id": "admin",
                "label": "Admin",
                "authenticated": True,
                "page_urls": [pages[0]["url"]],
            },
            {
                "persona_id": "user",
                "label": "User",
                "authenticated": True,
                "page_urls": [],
            },
        ]
    )
    persona_visibility["pages"] = pages
    matrix = build_visibility_matrix(modules=modules, persona_visibility=persona_visibility)
    persona_visibility["visibility_matrix"] = matrix

    auth = build_auth_intelligence(
        pages=pages,
        forms=forms,
        flows=flows,
        elements=elements,
        api_endpoints=api_endpoints,
        modules=modules,
        persona_visibility=persona_visibility,
        auth_signals={
            "authenticated": True,
            "session_type": "bearer",
            "cookie_names": ["session"],
            "blockers": [],
        },
        crawl_authenticated=True,
    )
    if auth.get("session_type") not in {"bearer", "mixed"}:
        print(f"FAIL session_type: {auth.get('session_type')}", file=sys.stderr)
        return False
    if auth.get("login_flow_id") != flow_id:
        print(f"FAIL login_flow_id: {auth.get('login_flow_id')}", file=sys.stderr)
        return False
    if auth.get("login_api_endpoint_id") != endpoint_id:
        print(f"FAIL login_api_endpoint_id: {auth.get('login_api_endpoint_id')}", file=sys.stderr)
        return False
    personas = auth.get("personas") or []
    if len(personas) < 2:
        print(f"FAIL personas count: {personas}", file=sys.stderr)
        return False
    if not auth.get("visibility_matrix"):
        print("FAIL visibility_matrix missing", file=sys.stderr)
        return False
    print("OK auth intelligence builder (login detection, personas, visibility_matrix)")
    return True


def _verify_appmap_integration() -> bool:
    app_id = uuid.uuid4()
    run_id = uuid.uuid4()
    page_id = uuid.uuid4()
    form_id = uuid.uuid4()
    element_id = uuid.uuid4()

    session = get_session_factory()()
    try:
        session.add(
            Application(
                app_id=app_id,
                name=f"verify-auth-intel-{app_id.hex[:8]}",
                base_url="https://example.com/app/",
            )
        )
        session.add(
            Page(
                page_id=page_id,
                app_id=app_id,
                url="https://example.com/app/login",
                title="Login",
            )
        )
        session.add(
            Element(
                element_id=element_id,
                page_id=page_id,
                tag_name="input",
                attributes={"name": "password", "type": "password"},
            )
        )
        session.add(
            Form(
                form_id=form_id,
                app_id=app_id,
                page_id=page_id,
                method="post",
                attributes={"name": "login"},
                field_element_ids=[str(element_id)],
            )
        )
        session.add(
            PipelineRun(
                id=run_id,
                application_id=app_id,
                current_stage=PipelineStage.discover,
                status=PipelineStatus.completed,
                config={},
            )
        )
        session.flush()

        auth_path = artifact_storage_root() / "auth_signals" / str(app_id) / f"{run_id}.json"
        auth_path.parent.mkdir(parents=True, exist_ok=True)
        auth_payload = {
            "authenticated": True,
            "session_type": "cookie",
            "cookie_names": ["session"],
            "protected_page_ids": [],
            "protected_api_endpoint_ids": [],
        }
        auth_path.write_text(json.dumps(auth_payload), encoding="utf-8")
        session.add(
            Artifact(
                pipeline_run_id=run_id,
                type=ArtifactType.report,
                path=str(auth_path),
                size_bytes=auth_path.stat().st_size,
            )
        )

        persona_path = artifact_storage_root() / "persona_visibility" / str(app_id) / f"{run_id}.json"
        persona_path.parent.mkdir(parents=True, exist_ok=True)
        persona_payload = {
            "personas": [
                {"persona_id": "admin", "label": "Admin", "authenticated": True},
            ],
            "page_personas": {"https://example.com/app/login": ["admin"]},
            "pages": [{"page_id": str(page_id), "url": "https://example.com/app/login"}],
        }
        persona_path.write_text(json.dumps(persona_payload), encoding="utf-8")
        session.add(
            Artifact(
                pipeline_run_id=run_id,
                type=ArtifactType.report,
                path=str(persona_path),
                size_bytes=persona_path.stat().st_size,
            )
        )
        session.commit()

        document = load_appmap_for_application(session, app_id)
        if document is None:
            print("FAIL load_appmap_for_application returned None", file=sys.stderr)
            return False
        auth_intel = document.get("auth_intelligence") or {}
        if not auth_intel.get("authenticated"):
            print(f"FAIL auth_intelligence.authenticated: {auth_intel}", file=sys.stderr)
            return False
        if auth_intel.get("session_type") != "cookie":
            print(f"FAIL auth_intelligence.session_type: {auth_intel}", file=sys.stderr)
            return False
        if not auth_intel.get("personas"):
            print(f"FAIL auth_intelligence.personas empty: {auth_intel}", file=sys.stderr)
            return False
        print("OK appmap integration (auth_intelligence, personas)")
        return True
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


def main() -> int:
    print("verify:auth-intelligence")
    checks = [_verify_builder, _verify_appmap_integration]
    for check in checks:
        if not check():
            return 1
    print("verify:auth-intelligence OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
