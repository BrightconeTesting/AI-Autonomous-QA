"""API endpoint coverage derived from test runs and recommended test areas."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from aqa_shared.db.models import Flow, TestCase, TestRun, TestRunStatus


def _page_ids_for_flow(flow: Flow | None) -> set[str]:
    if flow is None:
        return set()
    steps = flow.sequence if isinstance(flow.sequence, list) else []
    page_ids: set[str] = set()
    for step in steps:
        if not isinstance(step, dict):
            continue
        page_id = step.get("page_id")
        if page_id:
            page_ids.add(str(page_id))
        target = str(step.get("url") or step.get("target") or "")
        if target:
            page_ids.add(target)
    return page_ids


def build_api_endpoint_coverage(
    db: Session,
    *,
    app_id: UUID,
    api_endpoints: list[dict],
    api_ui_mappings: list[dict],
    flows: list[dict],
    recommended_test_areas: list[dict] | None = None,
    include_failed_runs: bool = False,
) -> dict:
    """Infer covered vs untested API endpoints from executed test-case flows."""
    all_endpoint_ids = {
        str(endpoint.get("endpoint_id") or "")
        for endpoint in api_endpoints
        if endpoint.get("endpoint_id")
    }

    page_to_endpoints: dict[str, set[str]] = {}
    for mapping in api_ui_mappings:
        page_id = str(mapping.get("page_id") or "")
        endpoint_id = str(mapping.get("api_endpoint_id") or "")
        if not page_id or not endpoint_id:
            continue
        page_to_endpoints.setdefault(page_id, set()).add(endpoint_id)

    flow_by_id = {
        str(row.flow_id): row
        for row in db.scalars(select(Flow).where(Flow.app_id == app_id)).all()
    }
    flows_by_id = {str(item.get("flow_id") or ""): item for item in flows}

    statuses = [TestRunStatus.passed]
    if include_failed_runs:
        statuses.extend([TestRunStatus.failed, TestRunStatus.flaky])

    testcase_rows = list(db.scalars(select(TestCase).where(TestCase.app_id == app_id)).all())
    testcase_by_id = {str(row.testcase_id): row for row in testcase_rows}

    covered: set[str] = set()
    executed_testcase_ids: set[str] = set()

    runs = list(
        db.scalars(
            select(TestRun).where(TestRun.app_id == app_id, TestRun.status.in_(statuses))
        ).all()
    )

    for run in runs:
        summary = run.summary if isinstance(run.summary, dict) else {}
        for testcase_id in summary.get("testcase_ids") or []:
            executed_testcase_ids.add(str(testcase_id))

    if not executed_testcase_ids:
        for testcase in testcase_rows:
            if testcase.flow_id is not None:
                executed_testcase_ids.add(str(testcase.testcase_id))

    for testcase_id in executed_testcase_ids:
        testcase = testcase_by_id.get(testcase_id)
        if testcase is None or testcase.flow_id is None:
            continue
        flow = flow_by_id.get(str(testcase.flow_id))
        flow_doc = flows_by_id.get(str(testcase.flow_id))
        page_ids = _page_ids_for_flow(flow)
        if flow_doc:
            for step in flow_doc.get("steps") or []:
                if isinstance(step, dict) and step.get("page_id"):
                    page_ids.add(str(step.get("page_id")))
        for page_id in page_ids:
            covered |= page_to_endpoints.get(page_id, set())

    planned = {
        str(area.get("api_endpoint_id") or "")
        for area in (recommended_test_areas or [])
        if area.get("api_endpoint_id")
    }

    untested = all_endpoint_ids - covered
    unplanned = {endpoint_id for endpoint_id in untested if endpoint_id not in planned}

    return {
        "covered_endpoint_ids": sorted(covered),
        "planned_endpoint_ids": sorted(planned),
        "untested_endpoint_ids": sorted(untested),
        "unplanned_endpoint_ids": sorted(unplanned),
    }
