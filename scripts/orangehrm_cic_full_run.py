#!/usr/bin/env python3
"""Full CIC crawl on OrangeHRM using app max_pages/max_depth — detailed delta report."""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
os.environ.setdefault("DATABASE_URL", "postgresql://aqa:aqa@localhost:5432/autonomous_qa")
os.environ.setdefault("ENCRYPTION_KEY", "0123456789abcdef" * 4)

APP_ID = "30b005f1-baee-4e01-9ae6-6886c7b44022"

if not os.getenv("ORANGEHRM_DEMO_USER", "").strip():
    os.environ["ORANGEHRM_DEMO_USER"] = json.dumps({"username": "Admin", "password": "admin123"})

from aqa_discovery.auth import load_auth_config  # noqa: E402
from aqa_discovery.crawl_settings import CrawlSettings  # noqa: E402
from aqa_discovery.crawler import CrawlSession  # noqa: E402
from aqa_discovery.types import CrawlResult, ElementSnapshot, PageSnapshot  # noqa: E402
from aqa_shared.db.models import Application  # noqa: E402
from aqa_shared.db.session import get_session_factory  # noqa: E402


def _element_key(el: ElementSnapshot) -> str:
    return el.interaction_key or el.semantic_selector or el.xpath_fallback or f"{el.tag_name}:{el.text_content or ''}"


def _element_label(el: ElementSnapshot) -> str:
    parts = [el.tag_name]
    if el.role:
        parts.append(f"role={el.role}")
    if el.text_content:
        parts.append(el.text_content.strip()[:60])
    return " | ".join(parts)


def _collect_page_elements(page: PageSnapshot) -> dict[str, list[str]]:
    """Return element_key -> list of state labels where seen."""
    by_key: dict[str, list[str]] = defaultdict(list)
    for el in page.elements:
        by_key[_element_key(el)].append("baseline")
    for state in page.states:
        label = state.state_key
        if state.trigger_interaction:
            trig = state.trigger_interaction
            label = f"{state.state_key} (via {trig.action_type}: {trig.text_content or trig.role})"
        for el in state.elements:
            by_key[_element_key(el)].append(label)
    return by_key


def _sample_state_only(page: PageSnapshot, state_only: set[str]) -> list[dict]:
    labels: dict[str, str] = {}
    for state in page.states:
        for el in state.elements:
            key = _element_key(el)
            if key in state_only:
                labels[key] = _element_label(el)
    return [{"key": k, "label": labels[k]} for k in list(state_only)[:8] if k in labels]


def _analyze(result: CrawlResult, label: str, elapsed: float) -> dict:
    all_urls = {p.url for p in result.pages}
    discovered_via_interaction: list[dict] = []
    for page in result.pages:
        for d in page.discovered_urls:
            discovered_via_interaction.append(
                {
                    "url": d.url,
                    "source_page": d.source_page_url,
                    "via": d.discovered_via,
                    "trigger": (
                        f"{d.trigger_interaction.action_type}: {d.trigger_interaction.text_content or d.trigger_interaction.role}"
                        if d.trigger_interaction
                        else None
                    ),
                    "in_crawl_queue": d.url in all_urls,
                }
            )

    pages_detail = []
    total_baseline = 0
    total_state_only = 0
    total_unique_keys = 0

    for page in result.pages:
        by_key = _collect_page_elements(page)
        baseline_keys = {_element_key(el) for el in page.elements}
        all_keys = set(by_key)
        state_only = all_keys - baseline_keys

        total_baseline += len(baseline_keys)
        total_state_only += len(state_only)
        total_unique_keys += len(all_keys)

        pages_detail.append(
            {
                "url": page.url,
                "title": page.title,
                "depth": page.depth,
                "baseline_elements": len(baseline_keys),
                "states": len(page.states),
                "transitions": len(page.transitions),
                "unique_elements_all_states": len(all_keys),
                "elements_only_in_states": len(state_only),
                "discovered_urls": [d.url for d in page.discovered_urls],
                "state_summaries": [
                    {
                        "state_key": s.state_key,
                        "element_count": len(s.elements),
                        "trigger": (
                            f"{s.trigger_interaction.action_type}: {s.trigger_interaction.text_content or s.trigger_interaction.role}"
                            if s.trigger_interaction
                            else None
                        ),
                    }
                    for s in page.states
                ],
                "sample_state_only_elements": _sample_state_only(page, state_only),
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
        "page_urls": sorted(p.url for p in result.pages),
        "total_states": sum(len(p.states) for p in result.pages),
        "total_transitions": sum(len(p.transitions) for p in result.pages),
        "total_discovered_urls": len(discovered_via_interaction),
        "discovered_via_interaction": discovered_via_interaction,
        "element_totals": {
            "baseline_elements_sum": total_baseline,
            "state_only_elements_sum": total_state_only,
            "unique_keys_sum": total_unique_keys,
        },
        "pages": pages_detail,
    }


def _compare(bfs: dict, cic: dict) -> dict:
    bfs_urls = set(bfs["page_urls"])
    cic_urls = set(cic["page_urls"])
    new_pages = sorted(cic_urls - bfs_urls)
    only_bfs = sorted(bfs_urls - cic_urls)

    bfs_elements: dict[str, set[str]] = {}
    cic_elements: dict[str, set[str]] = {}

    for page in bfs["pages"]:
        bfs_elements[page["url"]] = set()
    for page in cic["pages"]:
        cic_elements[page["url"]] = set()

    # Rebuild from raw - we need keys per URL; use pages detail counts for summary
    # Load from stored page summaries - for delta we need element keys
    return {
        "pages": {
            "bfs_count": len(bfs_urls),
            "cic_count": len(cic_urls),
            "new_pages_from_cic": new_pages,
            "only_in_bfs": only_bfs,
            "shared": sorted(bfs_urls & cic_urls),
        },
        "states": {
            "bfs": bfs["total_states"],
            "cic": cic["total_states"],
            "cic_extra": cic["total_states"] - bfs["total_states"],
        },
        "transitions": {
            "bfs": bfs["total_transitions"],
            "cic": cic["total_transitions"],
        },
        "discovered_urls": {
            "cic_total": cic["total_discovered_urls"],
            "via_interaction": [
                d for d in cic["discovered_via_interaction"] if d["via"] == "interaction"
            ],
        },
        "elements": {
            "bfs_baseline_sum": bfs["element_totals"]["baseline_elements_sum"],
            "cic_baseline_sum": cic["element_totals"]["baseline_elements_sum"],
            "cic_state_only_sum": cic["element_totals"]["state_only_elements_sum"],
            "cic_unique_sum": cic["element_totals"]["unique_keys_sum"],
            "cic_extra_baseline": cic["element_totals"]["baseline_elements_sum"]
            - bfs["element_totals"]["baseline_elements_sum"],
        },
        "interactions_executed": cic["stats"].get("interactions_executed", 0),
        "elapsed_seconds": {
            "bfs": bfs["elapsed_seconds"],
            "cic": cic["elapsed_seconds"],
        },
    }


def _compare_elements_detailed(bfs_result: CrawlResult, cic_result: CrawlResult) -> dict:
    """Per-URL and global element deltas."""
    bfs_by_url = {p.url: _collect_page_elements(p) for p in bfs_result.pages}
    cic_by_url = {p.url: _collect_page_elements(p) for p in cic_result.pages}

    bfs_all_keys: set[str] = set()
    for keys in bfs_by_url.values():
        bfs_all_keys |= set(keys)

    cic_all_keys: set[str] = set()
    for keys in cic_by_url.values():
        cic_all_keys |= set(keys)

    global_new_keys = cic_all_keys - bfs_all_keys

    per_page = []
    for url, cic_keys in cic_by_url.items():
        bfs_keys = set(bfs_by_url.get(url, {}))
        cic_key_set = set(cic_keys)
        new_on_page = cic_key_set - bfs_keys
        if new_on_page or url not in bfs_by_url:
            # Resolve labels from cic result page
            cic_page = next(p for p in cic_result.pages if p.url == url)
            labels = {}
            for el in cic_page.elements:
                labels[_element_key(el)] = _element_label(el)
            for state in cic_page.states:
                for el in state.elements:
                    labels[_element_key(el)] = _element_label(el)

            per_page.append(
                {
                    "url": url,
                    "title": cic_page.title,
                    "is_new_page": url not in bfs_by_url,
                    "bfs_element_count": len(bfs_keys),
                    "cic_element_count": len(cic_key_set),
                    "new_elements_count": len(new_on_page),
                    "new_elements": [
                        {"key": k, "label": labels.get(k, k), "seen_in_states": cic_keys[k]}
                        for k in sorted(new_on_page)
                    ],
                }
            )

    per_page.sort(key=lambda x: (-x["new_elements_count"], x["url"]))

    return {
        "global_new_element_keys": len(global_new_keys),
        "global_new_elements_sample": sorted(global_new_keys)[:30],
        "per_page": per_page,
    }


def main() -> int:
    session = get_session_factory()()
    app = session.get(Application, uuid.UUID(APP_ID))
    if app is None:
        print("FAIL: OrangeHRM app not found", file=sys.stderr)
        return 1

    app_config = dict(app.crawl_config or {})
    max_pages = int(app_config.get("max_pages", 100))
    max_depth = int(app_config.get("max_depth", 5))

    base_overrides = {
        **app_config,
        "respect_robots_txt": False,
    }
    bfs_overrides = {**base_overrides, "enable_cic": False}
    cic_overrides = {
        **base_overrides,
        "enable_cic": True,
        "cic_mode": "full",
        "cic_rich_interactions": True,
        "cic_in_page_only": False,
        "cic_enable_tables": True,
        "cic_enable_date_pickers": True,
        "cic_enable_iframes": True,
    }

    print("=" * 70)
    print("OrangeHRM — Full CIC crawl (app max_pages / max_depth)")
    print("=" * 70)
    print(f"App:        {app.name}")
    print(f"Base URL:   {app.base_url}")
    print(f"max_pages:  {max_pages}")
    print(f"max_depth:  {max_depth}")
    print(f"CIC mode:   full")
    print(f"Started:    {datetime.now(timezone.utc).isoformat()}")
    print()

    print("--- Phase 1: BFS baseline ---")
    t0 = time.monotonic()
    bfs_result, _ = _run(bfs_overrides, label="BFS")
    bfs_elapsed = time.monotonic() - t0
    if bfs_result.halted:
        print(f"WARN BFS halted: {bfs_result.halt_reason}")
    bfs_summary = _analyze(bfs_result, "bfs_only", bfs_elapsed)
    print(
        f"BFS done: {bfs_summary['pages_crawled']} pages, "
        f"{bfs_summary['element_totals']['baseline_elements_sum']} baseline elements, "
        f"{bfs_elapsed:.1f}s"
    )
    print()

    print("--- Phase 2: CIC full ---")
    t0 = time.monotonic()
    cic_result, _ = _run(cic_overrides, label="CIC")
    cic_elapsed = time.monotonic() - t0
    if cic_result.halted:
        print(f"WARN CIC halted: {cic_result.halt_reason}")
    cic_summary = _analyze(cic_result, "cic_full", cic_elapsed)
    print(
        f"CIC done: {cic_summary['pages_crawled']} pages, "
        f"{cic_summary['total_states']} states, "
        f"{cic_summary['stats'].get('interactions_executed', 0)} interactions, "
        f"{cic_elapsed:.1f}s"
    )
    print()

    comparison = _compare(bfs_summary, cic_summary)
    element_delta = _compare_elements_detailed(bfs_result, cic_result)

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(json.dumps(comparison, indent=2))
    print()
    print("--- New pages found by CIC (not in BFS crawl) ---")
    for url in comparison["pages"]["new_pages_from_cic"]:
        print(f"  + {url}")
    if not comparison["pages"]["new_pages_from_cic"]:
        print("  (none — same page set; check interaction-discovered URLs below)")
    print()
    print("--- URLs discovered via CIC interactions ---")
    for d in comparison["discovered_urls"]["via_interaction"]:
        queued = "queued" if d["in_crawl_queue"] else "not queued"
        print(f"  {d['url']}")
        print(f"    source: {d['source_page']} | trigger: {d['trigger']} | {queued}")
    print()
    print("--- Top pages with most new elements (CIC vs BFS on same URL) ---")
    for row in element_delta["per_page"][:15]:
        tag = " [NEW PAGE]" if row["is_new_page"] else ""
        print(f"  {row['new_elements_count']} new @ {row['url']}{tag}")
        for el in row["new_elements"][:5]:
            print(f"      - {el['label']}")
        if row["new_elements_count"] > 5:
            print(f"      ... +{row['new_elements_count'] - 5} more")
    print()
    print(f"Global new element keys (CIC not in BFS): {element_delta['global_new_element_keys']}")

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "app_id": APP_ID,
        "config": {
            "max_pages": max_pages,
            "max_depth": max_depth,
            "cic_mode": "full",
            "cic_overrides": cic_overrides,
        },
        "bfs_only": bfs_summary,
        "cic_full": cic_summary,
        "comparison": comparison,
        "element_delta": element_delta,
    }

    out = ROOT / "artifacts" / "orangehrm_cic_full_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print()
    print(f"Full report: {out}")
    print("=" * 70)
    return 0


def _run(overrides: dict, *, label: str = "crawl") -> tuple[CrawlResult, float]:
    session = get_session_factory()()
    app = session.get(Application, uuid.UUID(APP_ID))
    if app is None:
        raise ValueError("OrangeHRM app not found")

    settings = CrawlSettings.from_crawl_config(app.base_url, app.crawl_config, overrides=overrides)
    start_urls = [app.base_url, *(app.seed_urls or [])]
    auth_config = load_auth_config(app.auth_config if isinstance(app.auth_config, dict) else {})
    session.close()

    page_num = 0
    started = time.monotonic()

    def on_progress(snapshot: PageSnapshot, stats) -> None:
        nonlocal page_num
        page_num += 1
        states = len(snapshot.states)
        discovered = len(snapshot.discovered_urls)
        cic_tag = f" states={states}" if states else ""
        disc_tag = f" discovered={discovered}" if discovered else ""
        print(
            f"  [{label}] page {page_num}/{settings.max_pages} "
            f"depth={snapshot.depth} "
            f"elements={len(snapshot.elements)}{cic_tag}{disc_tag} "
            f"interactions={stats.interactions_executed} "
            f"| {snapshot.title[:50] or snapshot.url[:50]}",
            flush=True,
        )

    with CrawlSession(page_timeout_ms=settings.page_timeout_ms) as crawl:
        if auth_config:
            crawl.authenticate(auth_config=auth_config, base_url=app.base_url)
        result = crawl.crawl_bfs(start_urls, settings, on_progress=on_progress)
        result.authenticated = bool(auth_config)

    return result, time.monotonic() - started


if __name__ == "__main__":
    raise SystemExit(main())
