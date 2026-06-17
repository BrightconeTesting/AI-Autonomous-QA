#!/usr/bin/env python3
"""Run Day 19 discover against OrangeHRM and print full persistence report."""

from __future__ import annotations

import json
import os
import sys
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
os.environ.setdefault("DATABASE_URL", "postgresql://aqa:aqa@localhost:5432/autonomous_qa")

APP_ID = "30b005f1-baee-4e01-9ae6-6886c7b44022"

from aqa_discovery.worker import crawl_application  # noqa: E402
from aqa_shared.db.models import (  # noqa: E402
    Application,
    Artifact,
    ArtifactType,
    Element,
    Page,
    PipelineRun,
)
from aqa_shared.db.session import get_session_factory  # noqa: E402


def _role_breakdown(elements: list[Element]) -> dict[str, int]:
    return dict(Counter((e.role or e.tag_name or "unknown") for e in elements))


def _tag_breakdown(elements: list[Element]) -> dict[str, int]:
    return dict(Counter(e.tag_name for e in elements))


def main() -> int:
    if not os.getenv("ORANGEHRM_DEMO_USER", "").strip():
        os.environ["ORANGEHRM_DEMO_USER"] = json.dumps(
            {"username": "Admin", "password": "admin123"}
        )
        print("NOTE: ORANGEHRM_DEMO_USER not in .env — using demo Admin/admin123\n")

    session = get_session_factory()()
    app = session.get(Application, uuid.UUID(APP_ID))
    if app is None:
        print(f"FAIL: Application {APP_ID} not found", file=sys.stderr)
        return 1

    pipeline_run = PipelineRun(application_id=app.app_id, config={"source": "day19_report"})
    session.add(pipeline_run)
    session.commit()
    session.refresh(pipeline_run)
    pipeline_run_id = str(pipeline_run.id)

    print("=" * 60)
    print("OrangeHRM Day 19 — Discover + Persist Report")
    print("=" * 60)
    print(f"App:           {app.name} ({APP_ID})")
    print(f"Base URL:      {app.base_url}")
    print(f"Pipeline run:  {pipeline_run_id}")
    print(f"Started:       {datetime.utcnow().isoformat()}Z")
    print()

    started = datetime.utcnow()
    result = crawl_application(
        APP_ID,
        pipeline_run_id=pipeline_run_id,
        persist=True,
        db=session,
    )
    elapsed = (datetime.utcnow() - started).total_seconds()

    session.expire_all()
    app = session.get(Application, uuid.UUID(APP_ID))
    run = session.get(PipelineRun, pipeline_run.id)
    pages = session.query(Page).filter(Page.app_id == app.app_id).order_by(Page.discovered_at).all()
    elements = (
        session.query(Element)
        .join(Page)
        .filter(Page.app_id == app.app_id)
        .all()
    )
    artifacts = (
        session.query(Artifact)
        .filter(
            Artifact.pipeline_run_id == pipeline_run.id,
            Artifact.type == ArtifactType.screenshot,
        )
        .all()
    )

    report = {
        "crawl": {
            "elapsed_seconds": round(elapsed, 1),
            "authenticated": result.authenticated,
            "halted": result.halted,
            "halt_reason": result.halt_reason,
            "halt_url": result.halt_url,
            "stats": result.stats.model_dump(),
            "pages_in_memory": len(result.pages),
        },
        "pipeline_run": {
            "id": str(run.id),
            "status": run.status.value if hasattr(run.status, "value") else str(run.status),
            "current_stage": run.current_stage.value if hasattr(run.current_stage, "value") else str(run.current_stage),
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "ended_at": run.ended_at.isoformat() if run.ended_at else None,
            "error_message": run.error_message,
            "config": dict(run.config or {}),
        },
        "application": {
            "last_crawl_at": app.last_crawl_at.isoformat() if app.last_crawl_at else None,
        },
        "database": {
            "page_count": len(pages),
            "element_count": len(elements),
            "artifact_count": len(artifacts),
            "roles": _role_breakdown(elements),
            "tags": _tag_breakdown(elements),
        },
        "pages": [],
        "sample_elements_by_page": {},
    }

    print("--- CRAWL RESULT ---")
    print(json.dumps(report["crawl"], indent=2))
    print()
    print("--- PIPELINE RUN ---")
    print(json.dumps(report["pipeline_run"], indent=2))
    print()
    print("--- DATABASE SUMMARY ---")
    print(json.dumps(report["database"], indent=2))
    print()

    for page in pages:
        page_elements = [e for e in elements if e.page_id == page.page_id]
        page_info = {
            "page_id": str(page.page_id),
            "url": page.url,
            "title": page.title,
            "screenshot_path": page.screenshot_path,
            "discovered_at": page.discovered_at.isoformat() if page.discovered_at else None,
            "element_count": len(page_elements),
        }
        report["pages"].append(page_info)
        report["sample_elements_by_page"][page.url] = [
            {
                "tag": e.tag_name,
                "role": e.role,
                "text": (e.text_content or "")[:80],
                "semantic_selector": e.semantic_selector,
                "attributes": dict(e.attributes or {}),
            }
            for e in page_elements[:8]
        ]

    print("--- ALL PAGES ---")
    for p in report["pages"]:
        print(f"  [{p['element_count']:3d} elems] {p['title'][:50] if p['title'] else '?'}")
        print(f"           {p['url']}")
        if p["screenshot_path"]:
            exists = Path(p["screenshot_path"]).is_file()
            print(f"           screenshot: {p['screenshot_path']} ({'exists' if exists else 'MISSING'})")
    print()

    print("--- SAMPLE ELEMENTS (first 8 per page) ---")
    for url, samples in report["sample_elements_by_page"].items():
        print(f"\n{url}")
        for s in samples:
            sel = s["semantic_selector"] or "(xpath only)"
            print(f"  {s['role'] or s['tag']:12} | {sel[:70]}")

    out_path = ROOT / "artifacts" / "orangehrm_day19_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print()
    print(f"Full JSON report: {out_path}")
    print("=" * 60)

    session.close()
    return 0 if pages and run.status.value == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
