#!/usr/bin/env python3
"""Verify AppMap flows + GET /apps/{id}/appmap (Day 20)."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ.setdefault("DATABASE_URL", "postgresql://aqa:aqa@localhost:5432/autonomous_qa")

from aqa_agents.discovery.appmap import build_and_persist_appmap  # noqa: E402
from aqa_agents.discovery.flows import build_flows_from_pages  # noqa: E402
from aqa_shared.db.models import Application, Flow, Page, PipelineStatus  # noqa: E402
from aqa_shared.db.session import get_session_factory  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aqa_api.main import app  # noqa: E402


def _verify_flow_builder() -> bool:
    pages = [
        {"page_id": "1", "url": "https://example.com/web/index.php/pim/list", "title": "PIM"},
        {"page_id": "2", "url": "https://example.com/web/index.php/pim/view", "title": "View"},
        {"page_id": "3", "url": "https://example.com/web/index.php/admin/users", "title": "Admin"},
    ]
    flows = build_flows_from_pages(pages)
    if len(flows) != 2:
        print(f"FAIL flow builder expected 2 flows, got {len(flows)}", file=sys.stderr)
        return False
    modules = {flow["module"] for flow in flows}
    if modules != {"pim", "admin"}:
        print(f"FAIL flow modules: {modules}", file=sys.stderr)
        return False
    print(f"OK flow builder: {len(flows)} flows from {len(pages)} pages")
    return True


def _verify_appmap_persist_and_api() -> bool:
    session = get_session_factory()()
    app_id = uuid.uuid4()
    pipeline_run_id = uuid.uuid4()
    try:
        session.add(
            Application(
                app_id=app_id,
                name=f"verify-appmap-{app_id.hex[:8]}",
                base_url="https://example.com/web/index.php/",
            )
        )
        session.add(
            Page(
                app_id=app_id,
                url="https://example.com/web/index.php/dashboard/index",
                title="Dashboard",
            )
        )
        session.add(
            Page(
                app_id=app_id,
                url="https://example.com/web/index.php/pim/viewEmployeeList",
                title="Employees",
            )
        )
        from aqa_shared.db.models import PipelineRun, PipelineStage, PipelineStatus

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
        )
        if result.flow_count < 1 or result.page_count != 2:
            print(f"FAIL appmap persist: {result}", file=sys.stderr)
            return False

        flow_rows = session.query(Flow).filter(Flow.app_id == app_id).count()
        if flow_rows != result.flow_count:
            print(f"FAIL flows table count: {flow_rows}", file=sys.stderr)
            return False
        if not Path(result.appmap_path).is_file():
            print(f"FAIL appmap artifact missing: {result.appmap_path}", file=sys.stderr)
            return False
        print(
            f"OK appmap persist: pages={result.page_count} elements={result.element_count} "
            f"flows={result.flow_count}"
        )
    finally:
        from aqa_shared.db.models import Artifact, Element

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

    client = TestClient(app)
    orangehrm_id = uuid.UUID("30b005f1-baee-4e01-9ae6-6886c7b44022")
    session = get_session_factory()()
    try:
        flow_count = session.query(Flow).filter(Flow.app_id == orangehrm_id).count()
        if flow_count < 1:
            from aqa_shared.db.models import PipelineRun

            latest_run = (
                session.query(PipelineRun)
                .filter(
                    PipelineRun.application_id == orangehrm_id,
                    PipelineRun.status == PipelineStatus.completed,
                )
                .order_by(PipelineRun.ended_at.desc())
                .first()
            )
            if latest_run is None:
                print("SKIP OrangeHRM appmap API: no completed pipeline run", file=sys.stderr)
                return True
            build_and_persist_appmap(
                application_id=orangehrm_id,
                pipeline_run_id=latest_run.id,
                db=session,
            )
    finally:
        session.close()

    resp = client.get(f"/api/v1/apps/{orangehrm_id}/appmap")
    if resp.status_code != 200:
        print(f"SKIP OrangeHRM appmap API: status={resp.status_code}", file=sys.stderr)
        return True

    body = resp.json()
    if body["stats"]["page_count"] < 1:
        print(f"FAIL OrangeHRM appmap empty: {body['stats']}", file=sys.stderr)
        return False
    if body["stats"]["flow_count"] < 1:
        print(f"FAIL OrangeHRM appmap has no flows: {body['stats']}", file=sys.stderr)
        return False
    if not body.get("pages") or not body.get("elements"):
        print("FAIL OrangeHRM appmap missing pages/elements arrays", file=sys.stderr)
        return False
    print(
        f"OK GET /apps/{{id}}/appmap: pages={body['stats']['page_count']} "
        f"elements={body['stats']['element_count']} flows={body['stats']['flow_count']}"
    )
    return True


def main() -> int:
    print("verify:appmap")
    checks = [_verify_flow_builder, _verify_appmap_persist_and_api]
    for check in checks:
        if not check():
            return 1
    print("verify:appmap OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
