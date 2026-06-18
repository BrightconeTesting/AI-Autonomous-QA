#!/usr/bin/env python3
"""Persist CIC discovery to DB via the production crawl path (pipeline_run + persist + AppMap v2).

Report-only scripts (orangehrm_cic_full_run.py) do NOT write to the database.
This script uses crawl_application(persist=True, pipeline_run_id=...) then build_and_persist_appmap().
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
os.environ.setdefault("DATABASE_URL", "postgresql://aqa:aqa@localhost:5432/autonomous_qa")
os.environ.setdefault("ENCRYPTION_KEY", "0123456789abcdef" * 4)

ORANGEHRM_APP_ID = "30b005f1-baee-4e01-9ae6-6886c7b44022"

from sqlalchemy import select

from aqa_agents.discovery.appmap import build_and_persist_appmap, load_appmap_for_application  # noqa: E402
from aqa_discovery.worker import crawl_application  # noqa: E402
from aqa_shared.db.models import (  # noqa: E402
    Application,
    Element,
    Flow,
    Page,
    PageDiscovery,
    PageState,
    PipelineRun,
    StateTransition,
)
from aqa_shared.db.session import get_session_factory  # noqa: E402


def _default_cic_overrides(*, cic_mode: str, smoke: bool) -> dict:
    base = {
        "enable_cic": True,
        "cic_mode": cic_mode,
        "cic_rich_interactions": True,
        "cic_in_page_only": False,
        "cic_enable_tables": True,
        "cic_enable_date_pickers": True,
        "cic_enable_iframes": True,
        "respect_robots_txt": False,
    }
    if smoke:
        base.update({"max_pages": 3, "max_depth": 1})
    else:
        base.setdefault("max_pages", 100)
        base.setdefault("max_depth", 10)
    return base


def _db_totals(session, app_id: uuid.UUID) -> dict:
    pages = session.query(Page).filter(Page.app_id == app_id).count()
    states = session.query(PageState).join(Page).filter(Page.app_id == app_id).count()
    transitions = session.query(StateTransition).filter(StateTransition.app_id == app_id).count()
    discoveries = session.query(PageDiscovery).filter(PageDiscovery.app_id == app_id).count()
    elements_total = session.query(Element).join(Page).filter(Page.app_id == app_id).count()
    elements_with_state = (
        session.query(Element)
        .join(Page)
        .filter(Page.app_id == app_id, Element.state_id.is_not(None))
        .count()
    )
    flows = list(session.scalars(select(Flow).where(Flow.app_id == app_id)).all())
    flows_with_interactions = 0
    for flow in flows:
        steps = list(flow.sequence or [])
        if any((s.get("action") or "") not in ("navigate",) for s in steps if isinstance(s, dict)):
            flows_with_interactions += 1
    return {
        "pages": pages,
        "page_states": states,
        "state_transitions": transitions,
        "page_discoveries": discoveries,
        "elements_total": elements_total,
        "elements_with_state_id": elements_with_state,
        "flows_total": len(flows),
        "flows_with_click_select_hover": flows_with_interactions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="CIC discover with DB persistence + AppMap v2")
    parser.add_argument("--app-id", default=ORANGEHRM_APP_ID, help="Application UUID")
    parser.add_argument("--cic-mode", choices=("fast", "full"), default="full")
    parser.add_argument("--smoke", action="store_true", help="Quick run: max_pages=3, max_depth=1")
    parser.add_argument("--live", action="store_true", help="Print per-page progress lines")
    parser.add_argument(
        "--overrides",
        default="",
        help='JSON crawl_config_overrides merged on top (e.g. \'{"max_pages":5}\')',
    )
    args = parser.parse_args()

    if args.app_id == ORANGEHRM_APP_ID and not os.getenv("ORANGEHRM_DEMO_USER", "").strip():
        os.environ["ORANGEHRM_DEMO_USER"] = json.dumps({"username": "Admin", "password": "admin123"})

    app_uuid = uuid.UUID(args.app_id)
    extra_overrides = json.loads(args.overrides) if args.overrides.strip() else {}
    crawl_overrides = {**_default_cic_overrides(cic_mode=args.cic_mode, smoke=args.smoke), **extra_overrides}

    session = get_session_factory()()
    app = session.get(Application, app_uuid)
    if app is None:
        print(f"FAIL: application not found: {args.app_id}", file=sys.stderr)
        return 1

    pipeline_run = PipelineRun(
        application_id=app.app_id,
        config={
            "source": "cic_persist_discovery",
            "cic_mode": args.cic_mode,
            "smoke": args.smoke,
            "crawl_config_overrides": crawl_overrides,
        },
    )
    session.add(pipeline_run)
    session.commit()
    session.refresh(pipeline_run)
    pipeline_run_id = str(pipeline_run.id)

    print("=" * 70)
    print("CIC Persist Discovery — database + AppMap v2")
    print("=" * 70)
    print(f"App:            {app.name}")
    print(f"App ID:         {args.app_id}")
    print(f"Pipeline run:   {pipeline_run_id}")
    print(f"CIC mode:       {args.cic_mode}")
    print(f"Overrides:      {json.dumps(crawl_overrides, indent=2)}")
    print(f"Started:        {datetime.now(timezone.utc).isoformat()}")
    print()

    t0 = time.monotonic()
    try:
        result = crawl_application(
            args.app_id,
            crawl_overrides=crawl_overrides,
            pipeline_run_id=pipeline_run_id,
            persist=True,
            live_progress=args.live,
            db=session,
        )
    except Exception as exc:
        print(f"FAIL crawl: {exc}", file=sys.stderr)
        session.close()
        return 1

    elapsed = time.monotonic() - t0
    if result.halted:
        print(f"FAIL crawl halted: {result.halt_reason}", file=sys.stderr)
        session.close()
        return 1

    print()
    print(f"Crawl done: {len(result.pages)} pages, {result.stats.states_discovered} states, "
          f"{result.stats.interactions_executed} interactions, {elapsed:.1f}s")
    print()

    print("--- Building AppMap v2 ---")
    try:
        appmap_result = build_and_persist_appmap(
            application_id=app.app_id,
            pipeline_run_id=pipeline_run.id,
            db=session,
        )
    except Exception as exc:
        print(f"FAIL AppMap build: {exc}", file=sys.stderr)
        session.close()
        return 1

    session.expire_all()
    db_before = _db_totals(session, app.app_id)
    appmap_doc = load_appmap_for_application(session, app.app_id)

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "app_id": args.app_id,
        "pipeline_run_id": pipeline_run_id,
        "crawl_overrides": crawl_overrides,
        "crawl": {
            "elapsed_seconds": round(elapsed, 1),
            "authenticated": result.authenticated,
            "stats": result.stats.model_dump(),
            "pages_in_memory": len(result.pages),
        },
        "appmap": {
            "path": appmap_result.appmap_path,
            "hash": appmap_result.appmap_hash,
            "flow_count": appmap_result.flow_count,
            "schema_version": (appmap_doc or {}).get("schema_version"),
            "state_count_in_doc": len((appmap_doc or {}).get("states") or []),
            "transition_count_in_doc": len((appmap_doc or {}).get("transitions") or []),
        },
        "database": db_before,
    }

    print(json.dumps(report, indent=2))
    print()

    ok = (
        db_before["page_states"] > 0
        and db_before["state_transitions"] > 0
        and db_before["elements_with_state_id"] > 0
        and (appmap_doc or {}).get("schema_version") == 2
    )
    print(f"CIC persistence OK: {'YES' if ok else 'NO / INCOMPLETE'}")
    print(f"AppMap artifact: {appmap_result.appmap_path}")

    out = ROOT / "artifacts" / f"cic_persist_{args.app_id[:8]}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report: {out}")
    print("=" * 70)

    session.close()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
