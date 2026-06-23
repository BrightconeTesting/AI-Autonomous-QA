#!/usr/bin/env python3
"""Verify G3 — SPA route discovery and AppMap integration."""

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
from aqa_shared.discovery.spa_routes import build_spa_routes, infer_path_pattern  # noqa: E402
from aqa_shared.db.models import (  # noqa: E402
    Application,
    Artifact,
    ArtifactType,
    Page,
    PageDiscovery,
    PipelineRun,
    PipelineStage,
    PipelineStatus,
)
from aqa_shared.db.session import get_session_factory  # noqa: E402


def _verify_builder() -> bool:
    page_id = str(uuid.uuid4())
    pages = [
        {
            "page_id": page_id,
            "url": "https://example.com/app/#/users/42",
            "title": "Users",
        }
    ]
    modules = [
        {
            "module_id": "users",
            "name": "Users",
            "pages": [page_id],
            "features": [],
        }
    ]
    discoveries = [
        {
            "url": "https://example.com/app/#/settings",
            "discovered_via": "interaction",
            "source_page_id": page_id,
        }
    ]
    crawl_events = [
        {
            "from_url": "https://example.com/app/",
            "to_url": "https://example.com/app/users/99/profile",
            "discovery_method": "pushstate_listener",
            "source_page_url": "https://example.com/app/",
        }
    ]

    pattern = infer_path_pattern("https://example.com/app/users/99/profile")
    if pattern != "/app/users/:id/profile":
        print(f"FAIL infer_path_pattern: {pattern}", file=sys.stderr)
        return False

    routes = build_spa_routes(
        pages=pages,
        modules=modules,
        discoveries=discoveries,
        crawl_events=crawl_events,
    )
    if len(routes) < 2:
        print(f"FAIL expected >=2 spa routes, got {routes}", file=sys.stderr)
        return False

    pushstate = next((route for route in routes if route.get("discovery_method") == "pushstate_listener"), None)
    if pushstate is None:
        print(f"FAIL missing pushstate route: {routes}", file=sys.stderr)
        return False
    if float(pushstate.get("confidence") or 0) < 0.8:
        print(f"FAIL pushstate confidence too low: {pushstate}", file=sys.stderr)
        return False

    hash_route = next((route for route in routes if "/settings" in str(route.get("path_pattern"))), None)
    if hash_route is None:
        print(f"FAIL missing hash/settings route: {routes}", file=sys.stderr)
        return False

    print("OK spa route builder (path patterns, hash routes, pushstate events)")
    return True


def _verify_appmap_integration() -> bool:
    app_id = uuid.uuid4()
    run_id = uuid.uuid4()
    page_id = uuid.uuid4()

    session = get_session_factory()()
    try:
        session.add(
            Application(
                app_id=app_id,
                name=f"verify-spa-routes-{app_id.hex[:8]}",
                base_url="https://example.com/app/",
            )
        )
        session.add(
            Page(
                page_id=page_id,
                app_id=app_id,
                url="https://example.com/app/#/dashboard",
                title="Dashboard",
            )
        )
        session.flush()
        session.add(
            PageDiscovery(
                app_id=app_id,
                url="https://example.com/app/#/reports",
                discovered_via="interaction",
                source_page_id=page_id,
                trigger_action={},
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

        spa_path = artifact_storage_root() / "spa_routes" / str(app_id) / f"{run_id}.json"
        spa_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "events": [
                {
                    "from_url": "https://example.com/app/",
                    "to_url": "https://example.com/app/users/7",
                    "discovery_method": "pushstate_listener",
                    "source_page_url": "https://example.com/app/#/dashboard",
                }
            ]
        }
        spa_path.write_text(json.dumps(payload), encoding="utf-8")
        session.add(
            Artifact(
                pipeline_run_id=run_id,
                type=ArtifactType.report,
                path=str(spa_path),
                size_bytes=spa_path.stat().st_size,
            )
        )
        session.commit()

        document = load_appmap_for_application(session, app_id)
        if document is None:
            print("FAIL load_appmap_for_application returned None", file=sys.stderr)
            return False
        routes = document.get("spa_routes") or []
        if len(routes) < 2:
            print(f"FAIL spa_routes count expected >=2, got {routes}", file=sys.stderr)
            return False
        if (document.get("stats") or {}).get("spa_route_count", 0) < 2:
            print("FAIL stats.spa_route_count missing", file=sys.stderr)
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

    print("OK appmap integration (spa_routes[], stats.spa_route_count)")
    return True


def main() -> int:
    print("verify:spa-routes")
    checks = [_verify_builder, _verify_appmap_integration]
    for check in checks:
        if not check():
            return 1
    print("verify:spa-routes OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
