#!/usr/bin/env python3
"""Verify CIC data was persisted to the database for an application."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
os.environ.setdefault("DATABASE_URL", "postgresql://aqa:aqa@localhost:5432/autonomous_qa")

ORANGEHRM_APP_ID = "30b005f1-baee-4e01-9ae6-6886c7b44022"

from sqlalchemy import select

from aqa_agents.discovery.appmap import load_appmap_for_application  # noqa: E402
from aqa_shared.db.models import Element, Flow, Page, PageDiscovery, PageState, StateTransition  # noqa: E402
from aqa_shared.db.session import get_session_factory  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-id", default=ORANGEHRM_APP_ID)
    args = parser.parse_args()

    app_id = uuid.UUID(args.app_id)
    session = get_session_factory()()

    pages = session.query(Page).filter(Page.app_id == app_id).count()
    states = session.query(PageState).join(Page).filter(Page.app_id == app_id).count()
    transitions = session.query(StateTransition).filter(StateTransition.app_id == app_id).count()
    discoveries = session.query(PageDiscovery).filter(PageDiscovery.app_id == app_id).count()
    elements_with_state = (
        session.query(Element)
        .join(Page)
        .filter(Page.app_id == app_id, Element.state_id.is_not(None))
        .count()
    )
    flows = list(session.scalars(select(Flow).where(Flow.app_id == app_id)).all())
    interaction_flows = 0
    for flow in flows:
        steps = list(flow.sequence or [])
        if any(isinstance(s, dict) and s.get("action") not in (None, "navigate") for s in steps):
            interaction_flows += 1

    appmap = load_appmap_for_application(session, app_id)
    session.close()

    checks = {
        "pages_gt_0": pages > 0,
        "page_states_gt_0": states > 0,
        "transitions_gt_0": transitions > 0,
        "elements_with_state_gt_0": elements_with_state > 0,
        "appmap_schema_v2": (appmap or {}).get("schema_version") == 2,
        "appmap_has_states": len((appmap or {}).get("states") or []) > 0,
        "flows_with_interactions_gt_0": interaction_flows > 0,
    }

    summary = {
        "app_id": args.app_id,
        "pages": pages,
        "page_states": states,
        "state_transitions": transitions,
        "page_discoveries": discoveries,
        "elements_with_state_id": elements_with_state,
        "flows_total": len(flows),
        "flows_with_interaction_steps": interaction_flows,
        "appmap_schema_version": (appmap or {}).get("schema_version"),
        "checks": checks,
        "passed": all(checks.values()),
    }

    print(json.dumps(summary, indent=2))
    if not summary["passed"]:
        failed = [k for k, v in checks.items() if not v]
        print(f"FAIL: {', '.join(failed)}", file=sys.stderr)
        return 1
    print("verify_cic_persist: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
