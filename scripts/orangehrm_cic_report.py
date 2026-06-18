#!/usr/bin/env python3
"""Compare BFS-only vs CIC-enabled crawl on OrangeHRM Demo."""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
os.environ.setdefault("DATABASE_URL", "postgresql://aqa:aqa@localhost:5432/autonomous_qa")
os.environ.setdefault("ENCRYPTION_KEY", "0123456789abcdef" * 4)

APP_ID = "30b005f1-baee-4e01-9ae6-6886c7b44022"

if not os.getenv("ORANGEHRM_DEMO_USER", "").strip():
    os.environ["ORANGEHRM_DEMO_USER"] = json.dumps({"username": "Admin", "password": "admin123"})

from aqa_agents.discovery.appmap import build_and_persist_appmap  # noqa: E402
from aqa_discovery.types import CrawlResult, PageSnapshot  # noqa: E402
from aqa_discovery.worker import crawl_application  # noqa: E402
from aqa_shared.db.models import (  # noqa: E402
    Application,
    Element,
    Page,
    PageDiscovery,
    PageState,
    PipelineRun,
    StateTransition,
)
from aqa_shared.db.session import get_session_factory  # noqa: E402

# Conservative limits for repeatable OrangeHRM test
CRAWL_OVERRIDES = {
    "max_pages": 5,
    "max_depth": 2,
    "respect_robots_txt": False,
    "max_states_per_url": 12,
    "max_interactions_per_url": 25,
    "max_interactions_per_state": 5,
    "max_states_total": 50,
    "interaction_wait_ms": 1000,
    "interaction_wait_strategy": "dom_stable",
}


def _summarize_result(label: str, result: CrawlResult, elapsed: float) -> dict:
    all_state_elements: list[str] = []
    pages_detail = []
    for page in result.pages:
        state_count = len(page.states)
        transition_count = len(page.transitions)
        baseline_count = len(page.elements)
        state_element_counts = [len(s.elements) for s in page.states]
        unique_texts: set[str] = set()
        for state in page.states:
            for el in state.elements:
                if el.text_content:
                    unique_texts.add(el.text_content.strip()[:80])
                all_state_elements.append(el.interaction_key or el.semantic_selector or el.tag_name)

        pages_detail.append(
            {
                "url": page.url,
                "title": page.title,
                "baseline_elements": baseline_count,
                "states": state_count,
                "transitions": transition_count,
                "elements_per_state": state_element_counts,
                "unique_element_texts_across_states": len(unique_texts),
                "discovered_urls": [d.url for d in page.discovered_urls],
                "sample_transitions": [
                    {
                        "from": t.from_state_key,
                        "to": t.to_state_key,
                        "action": t.action.text_content or t.action.role,
                    }
                    for t in page.transitions[:5]
                ],
            }
        )

    return {
        "label": label,
        "elapsed_seconds": round(elapsed, 1),
        "authenticated": result.authenticated,
        "halted": result.halted,
        "halt_reason": result.halt_reason,
        "stats": result.stats.model_dump(),
        "pages_crawled": len(result.pages),
        "total_states": sum(len(p.states) for p in result.pages),
        "total_transitions": sum(len(p.transitions) for p in result.pages),
        "total_discovered_urls": sum(len(p.discovered_urls) for p in result.pages),
        "pages": pages_detail,
    }


def _run_crawl(enable_cic: bool) -> tuple[CrawlResult, float]:
    overrides = {**CRAWL_OVERRIDES, "enable_cic": enable_cic}
    started = time.monotonic()
    result = crawl_application(APP_ID, crawl_overrides=overrides, persist=False)
    elapsed = time.monotonic() - started
    return result, elapsed


def _persist_cic_run(result: CrawlResult) -> dict:
    session = get_session_factory()()
    app = session.get(Application, uuid.UUID(APP_ID))
    if app is None:
        return {"error": "app not found"}

    run = PipelineRun(application_id=app.app_id, config={"source": "orangehrm_cic_test"})
    session.add(run)
    session.commit()
    session.refresh(run)

    from aqa_discovery.persist import persist_crawl_result, mark_pipeline_completed, update_last_crawl_at

    pr = persist_crawl_result(
        session,
        app_id=app.app_id,
        pipeline_run_id=run.id,
        crawl_result=result,
    )
    update_last_crawl_at(session, app.app_id)
    mark_pipeline_completed(
        session,
        run.id,
        page_count=pr.page_count,
        element_count=pr.element_count,
        state_count=pr.state_count,
    )

    appmap = build_and_persist_appmap(application_id=app.app_id, pipeline_run_id=run.id, db=session)

    states = session.query(PageState).join(Page).filter(Page.app_id == app.app_id).count()
    transitions = session.query(StateTransition).filter(StateTransition.app_id == app.app_id).count()
    discoveries = session.query(PageDiscovery).filter(PageDiscovery.app_id == app.app_id).count()
    elements_with_state = (
        session.query(Element)
        .join(Page)
        .filter(Page.app_id == app.app_id, Element.state_id.is_not(None))
        .count()
    )

    session.close()
    return {
        "pipeline_run_id": str(run.id),
        "persist": {
            "page_count": pr.page_count,
            "element_count": pr.element_count,
            "state_count": pr.state_count,
        },
        "db_totals": {
            "page_states": states,
            "state_transitions": transitions,
            "page_discoveries": discoveries,
            "elements_with_state_id": elements_with_state,
        },
        "appmap": {
            "schema_version": json.loads(Path(appmap.appmap_path).read_text()).get("schema_version"),
            "state_count": appmap.page_count,
            "flow_count": appmap.flow_count,
            "appmap_path": appmap.appmap_path,
        },
    }


def main() -> int:
    print("=" * 70)
    print("OrangeHRM CIC Validation — BFS-only vs CIC-enabled")
    print("=" * 70)
    print(f"App ID:    {APP_ID}")
    print(f"Overrides: {json.dumps(CRAWL_OVERRIDES, indent=2)}")
    print(f"Started:   {datetime.utcnow().isoformat()}Z")
    print()

    session = get_session_factory()()
    app = session.get(Application, uuid.UUID(APP_ID))
    if app is None:
        print("FAIL: OrangeHRM application not in database", file=sys.stderr)
        return 1
    print(f"Target:    {app.name}")
    print(f"Base URL:  {app.base_url}")
    session.close()
    print()

    print("--- Run 1: BFS only (enable_cic=false) ---")
    bfs_result, bfs_elapsed = _run_crawl(enable_cic=False)
    if bfs_result.halted:
        print(f"FAIL BFS halted: {bfs_result.halt_reason}", file=sys.stderr)
        return 1
    bfs_summary = _summarize_result("bfs_only", bfs_result, bfs_elapsed)
    print(json.dumps(bfs_summary, indent=2))
    print()

    print("--- Run 2: CIC enabled (enable_cic=true) ---")
    cic_result, cic_elapsed = _run_crawl(enable_cic=True)
    if cic_result.halted:
        print(f"FAIL CIC halted: {cic_result.halt_reason}", file=sys.stderr)
        return 1
    cic_summary = _summarize_result("cic_enabled", cic_result, cic_elapsed)
    print(json.dumps(cic_summary, indent=2))
    print()

    print("--- Comparison ---")
    comparison = {
        "pages_crawled": {
            "bfs": bfs_summary["pages_crawled"],
            "cic": cic_summary["pages_crawled"],
        },
        "total_states": {
            "bfs": bfs_summary["total_states"],
            "cic": cic_summary["total_states"],
        },
        "total_transitions": {
            "bfs": cic_summary["total_transitions"],
        },
        "interactions_executed": cic_summary["stats"].get("interactions_executed", 0),
        "skipped_interaction_safety": cic_summary["stats"].get("skipped_interaction_safety", 0),
        "elapsed_seconds": {
            "bfs": bfs_summary["elapsed_seconds"],
            "cic": cic_summary["elapsed_seconds"],
            "slowdown_factor": round(cic_summary["elapsed_seconds"] / max(bfs_summary["elapsed_seconds"], 0.1), 2),
        },
        "cic_improvement": {
            "extra_states": cic_summary["total_states"] - bfs_summary["total_states"],
            "states_per_page_avg": round(
                cic_summary["total_states"] / max(cic_summary["pages_crawled"], 1), 2
            ),
        },
    }
    print(json.dumps(comparison, indent=2))
    print()

    cic_working = (
        cic_summary["total_states"] > bfs_summary["total_states"]
        or cic_summary["total_transitions"] > 0
        or cic_summary["stats"].get("interactions_executed", 0) > 0
    )
    print(f"CIC working on OrangeHRM: {'YES' if cic_working else 'NO / INCONCLUSIVE'}")

    if cic_working:
        print()
        print("--- Run 3: Persist CIC results + AppMap v2 ---")
        persist_info = _persist_cic_run(cic_result)
        print(json.dumps(persist_info, indent=2))

    report = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "app_id": APP_ID,
        "crawl_overrides": CRAWL_OVERRIDES,
        "bfs_only": bfs_summary,
        "cic_enabled": cic_summary,
        "comparison": comparison,
        "cic_working": cic_working,
    }
    if cic_working:
        report["persist"] = persist_info

    out = ROOT / "artifacts" / "orangehrm_cic_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print()
    print(f"Full report: {out}")
    print("=" * 70)

    return 0 if cic_working and not cic_result.halted else 1


if __name__ == "__main__":
    raise SystemExit(main())
