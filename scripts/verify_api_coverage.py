#!/usr/bin/env python3
"""Verify API endpoint coverage inference."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import delete

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ["ENCRYPTION_KEY"] = os.getenv("ENCRYPTION_KEY") or ("0123456789abcdef" * 4)
os.environ.setdefault("DATABASE_URL", os.getenv("DATABASE_URL", ""))

from aqa_api.services.api_coverage import build_api_endpoint_coverage  # noqa: E402
from aqa_shared.db.models import Application, Flow, FlowSource, TestCase, TestPriority  # noqa: E402
from aqa_shared.db.session import get_session_factory  # noqa: E402


def main() -> int:
    print("verify:api-coverage")
    app_id = uuid.uuid4()
    flow_id = uuid.uuid4()
    page_id = str(uuid.uuid4())
    covered_ep = str(uuid.uuid4())
    untested_ep = str(uuid.uuid4())

    session = get_session_factory()()
    try:
        session.add(
            Application(
                app_id=app_id,
                name=f"verify-api-coverage-{app_id.hex[:8]}",
                base_url="https://example.com/app/",
            )
        )
        session.add(
            Flow(
                flow_id=flow_id,
                app_id=app_id,
                name="Dashboard flow",
                sequence=[{"action": "navigate", "page_id": page_id}],
                source=FlowSource.crawler,
            )
        )
        session.add(
            TestCase(
                app_id=app_id,
                flow_id=flow_id,
                name="Replay dashboard",
                priority=TestPriority.medium,
                steps=[],
            )
        )
        session.flush()

        coverage = build_api_endpoint_coverage(
            session,
            app_id=app_id,
            api_endpoints=[
                {"endpoint_id": covered_ep, "path": "/api/items"},
                {"endpoint_id": untested_ep, "path": "/api/reports"},
            ],
            api_ui_mappings=[
                {"page_id": page_id, "api_endpoint_id": covered_ep},
            ],
            flows=[{"flow_id": str(flow_id), "steps": [{"page_id": page_id}]}],
            recommended_test_areas=[
                {"area_id": "area-1", "api_endpoint_id": untested_ep},
            ],
        )

        if covered_ep not in coverage.get("covered_endpoint_ids", []):
            print(f"FAIL covered endpoint missing: {coverage}", file=sys.stderr)
            return 1
        if untested_ep not in coverage.get("untested_endpoint_ids", []):
            print(f"FAIL untested endpoint missing: {coverage}", file=sys.stderr)
            return 1
        if untested_ep not in coverage.get("planned_endpoint_ids", []):
            print(f"FAIL planned endpoint missing: {coverage}", file=sys.stderr)
            return 1
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

    print("OK api endpoint coverage")
    print("verify:api-coverage OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
