#!/usr/bin/env python3
"""Verify Phase H — execution feedback loop, incremental crawl, shadow DOM helpers."""

from __future__ import annotations

import sys

from aqa_discovery.crawler import CrawlSession
from aqa_discovery.crawl_settings import CrawlSettings
from aqa_discovery.page_fingerprint import (
    build_page_fingerprint_index,
    compute_page_content_fingerprint,
    merge_page_fingerprints,
)
from aqa_discovery.types import ElementSnapshot, PageSnapshot
from aqa_shared.discovery.feedback import (
    FAILURE_API_ERROR,
    FAILURE_AUTH_401,
    FAILURE_FLOW_STEP_TIMEOUT,
    FAILURE_LOCATOR_NOT_FOUND,
    append_feedback_to_crawl_config,
    apply_discovery_feedback,
    build_feedback_event,
    classify_execution_failure,
    urls_requiring_recrawl,
)


def _verify_failure_classification() -> bool:
    cases = [
        ("Timeout 15000ms exceeded waiting for locator('button')", {"action": "click"}, FAILURE_LOCATOR_NOT_FOUND),
        ("401 Unauthorized", {"action": "navigate"}, FAILURE_AUTH_401),
        ("Request failed with status code 503", {"action": "navigate"}, FAILURE_API_ERROR),
        ("locator.click: Timeout 15000ms exceeded.", {"action": "fill", "target": "getByLabel('Name')"}, FAILURE_FLOW_STEP_TIMEOUT),
    ]
    for error, step, expected in cases:
        got = classify_execution_failure(error, step=step)
        if got != expected:
            print(f"FAIL classify {error!r}: expected {expected}, got {got}", file=sys.stderr)
            return False
    print("OK failure classification")
    return True


def _verify_feedback_apply() -> bool:
    target = "getByRole('button', { name: 'Save' })"
    appmap = {
        "elements": [
            {
                "element_id": "el-1",
                "semantic_selector": target,
                "testability_score": 80,
            }
        ],
        "flows": [
            {
                "flow_id": "flow-1",
                "steps": [{"action": "click", "target": target}],
                "automation_complexity_score": 25,
            }
        ],
        "api_ui_mappings": [
            {
                "mapping_id": "map-1",
                "api_endpoint_id": "ep-1",
                "path_pattern": "/api/items",
                "confidence": 0.9,
            }
        ],
        "auth_intelligence": {"protected": []},
    }
    events = [
        build_feedback_event(
            failure_type=FAILURE_LOCATOR_NOT_FOUND,
            error_msg="waiting for locator",
            step={"action": "click", "target": target},
            page_url="https://example.com/app/settings",
        ),
        build_feedback_event(
            failure_type=FAILURE_FLOW_STEP_TIMEOUT,
            error_msg="Timeout exceeded",
            step={"action": "click", "target": target, "flow_id": "flow-1"},
        ),
        build_feedback_event(
            failure_type="api_error",
            error_msg="status code 500 on /api/items",
            step={"action": "navigate", "api_endpoint_id": "ep-1"},
        ),
        build_feedback_event(
            failure_type=FAILURE_AUTH_401,
            error_msg="401 Unauthorized",
            page_url="https://example.com/app/admin",
        ),
    ]
    updated = apply_discovery_feedback(appmap, events)
    element = updated["elements"][0]
    flow = updated["flows"][0]
    mapping = updated["api_ui_mappings"][0]
    protected = updated["auth_intelligence"]["protected"]

    if int(element["testability_score"]) != 65:
        print(f"FAIL element testability: {element['testability_score']}", file=sys.stderr)
        return False
    if int(flow["automation_complexity_score"]) != 35:
        print(f"FAIL flow complexity: {flow['automation_complexity_score']}", file=sys.stderr)
        return False
    if float(mapping["confidence"]) >= 0.9:
        print(f"FAIL mapping confidence not reduced: {mapping['confidence']}", file=sys.stderr)
        return False
    if "https://example.com/app/admin" not in protected:
        print(f"FAIL protected pages: {protected}", file=sys.stderr)
        return False
    if "https://example.com/app/settings" not in (updated.get("discovery_feedback_applied") or {}).get(
        "recrawl_urls", []
    ):
        print("FAIL recrawl_urls missing settings page", file=sys.stderr)
        return False
    print("OK apply_discovery_feedback adjustments")
    return True


def _verify_feedback_storage_and_recrawl() -> bool:
    config = append_feedback_to_crawl_config(
        {},
        build_feedback_event(
            failure_type=FAILURE_LOCATOR_NOT_FOUND,
            error_msg="not found",
            page_url="https://example.com/app/dashboard",
            step={"action": "click", "target": "getByText('Go')"},
        ),
    )
    events = config.get("discovery_feedback") or []
    if len(events) != 1:
        print(f"FAIL append feedback: {events}", file=sys.stderr)
        return False
    recrawl = urls_requiring_recrawl(events)
    if "https://example.com/app/dashboard" not in recrawl:
        print(f"FAIL recrawl urls: {recrawl}", file=sys.stderr)
        return False
    print("OK feedback storage + recrawl urls")
    return True


def _verify_page_fingerprints() -> bool:
    elements = [
        ElementSnapshot(tag_name="button", role="button", text_content="Save", semantic_selector="getByText('Save')"),
    ]
    fp1 = compute_page_content_fingerprint(
        url="https://example.com/app/",
        title="Home",
        elements=elements,
    )
    fp2 = compute_page_content_fingerprint(
        url="https://example.com/app/",
        title="Home",
        elements=elements,
    )
    if fp1 != fp2:
        print(f"FAIL page fingerprint mismatch: {fp1} vs {fp2}", file=sys.stderr)
        return False

    page = PageSnapshot(
        url="https://example.com/app/dashboard",
        title="Dashboard",
        status=200,
        html_length=100,
        elements=elements,
        content_fingerprint=fp1,
    )
    index = build_page_fingerprint_index([page])
    merged = merge_page_fingerprints({"https://example.com/app": "old"}, index)
    if merged["https://example.com/app/dashboard"] != fp1:
        print(f"FAIL fingerprint index: {merged}", file=sys.stderr)
        return False
    print("OK page fingerprint helpers")
    return True


def _verify_incremental_skip_logic() -> bool:
    session = CrawlSession(
        known_fingerprints={"https://example.com/app/dashboard": "abc123"},
        recrawl_urls=set(),
        force_full_crawl=False,
    )
    settings = CrawlSettings(incremental_crawl=True)
    if not session._should_skip_deep_crawl("https://example.com/app/dashboard", "abc123", settings):
        print("FAIL expected skip unchanged page", file=sys.stderr)
        return False
    if session._should_skip_deep_crawl("https://example.com/app/dashboard", "changed", settings):
        print("FAIL should not skip changed fingerprint", file=sys.stderr)
        return False
    session.recrawl_urls.add("https://example.com/app/dashboard")
    if session._should_skip_deep_crawl("https://example.com/app/dashboard", "abc123", settings):
        print("FAIL should not skip recrawl flagged url", file=sys.stderr)
        return False
    print("OK incremental crawl skip logic")
    return True


def _verify_shadow_dom_extractor_present() -> bool:
    from aqa_discovery import extractors

    if "shadowRoot" not in extractors._SHADOW_PIERCE_EXTRACT_JS:
        print("FAIL shadow pierce JS missing shadowRoot walk", file=sys.stderr)
        return False
    if "pierce_shadow_dom" not in extractors.extract_elements.__code__.co_varnames:
        print("FAIL extract_elements missing pierce_shadow_dom param", file=sys.stderr)
        return False
    print("OK shadow DOM pierce extractor")
    return True


def main() -> int:
    print("verify:discovery-feedback")
    checks = [
        _verify_failure_classification,
        _verify_feedback_apply,
        _verify_feedback_storage_and_recrawl,
        _verify_page_fingerprints,
        _verify_incremental_skip_logic,
        _verify_shadow_dom_extractor_present,
    ]
    for check in checks:
        if not check():
            return 1
    print("verify:discovery-feedback OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
