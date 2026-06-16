#!/usr/bin/env python3
"""Verify SSE pipeline progress stream — Day 14."""

from __future__ import annotations

import json
import os
import sys
from itertools import islice
from pathlib import Path

from dotenv import load_dotenv
from fastapi.testclient import TestClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ["ENCRYPTION_KEY"] = os.getenv("ENCRYPTION_KEY") or ("0123456789abcdef" * 4)
os.environ.setdefault("DATABASE_URL", os.getenv("DATABASE_URL", ""))
os.environ.setdefault("REDIS_URL", os.getenv("REDIS_URL", "redis://localhost:6379"))

from aqa_api.config import settings
from aqa_api.main import app
from aqa_api.services.sse import stream_pipeline_events
from aqa_shared.sse import PipelineEventType, list_pipeline_events

APP_PAYLOAD = {
    "name": "Verify SSE App",
    "base_url": "https://juice-shop.herokuapp.com",
    "seed_urls": [],
    "crawl_config": {"max_pages": 5},
}


def _parse_sse_chunk(chunk: str) -> dict[str, str | dict]:
    event_type: str | None = None
    event_id: str | None = None
    data: dict | None = None
    for line in chunk.strip().splitlines():
        if line.startswith("event:"):
            event_type = line.split(":", 1)[1].strip()
        elif line.startswith("id:"):
            event_id = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data = json.loads(line.split(":", 1)[1].strip())
    if event_type is None or data is None:
        raise ValueError(f"invalid SSE chunk: {chunk!r}")
    return {"event": event_type, "id": event_id, "data": data}


def main() -> int:
    print("verify:sse")
    client = TestClient(app)

    create = client.post("/api/v1/apps", json=APP_PAYLOAD)
    if create.status_code != 201:
        print(f"FAIL create app: {create.status_code} {create.text}", file=sys.stderr)
        return 1
    app_id = create.json()["app_id"]

    discover = client.post(f"/api/v1/apps/{app_id}/discover", json={"force": False})
    if discover.status_code != 202:
        print(f"FAIL discover: {discover.status_code} {discover.text}", file=sys.stderr)
        return 1
    pipeline_run_id = discover.json()["pipeline_run_id"]
    print(f"OK POST /apps/{{id}}/discover: pipeline_run_id={pipeline_run_id}")

    stored = list_pipeline_events(pipeline_run_id)
    if not any(event.event == PipelineEventType.stage_started for event in stored):
        print("FAIL stage_started not published to Redis event log", file=sys.stderr)
        return 1
    print("OK stage_started stored in Redis event log")

    unknown = client.get("/api/v1/pipeline-runs/00000000-0000-0000-0000-000000000099/stream")
    if unknown.status_code != 404:
        print(f"FAIL stream 404: expected 404 got {unknown.status_code}", file=sys.stderr)
        return 1
    print("OK GET /pipeline-runs/{id}/stream returns 404 for unknown id")

    frames = list(
        islice(
            stream_pipeline_events(
                pipeline_run_id,
                redis_url=settings.redis_url,
            ),
            1,
        )
    )
    if not frames:
        print("FAIL SSE generator produced no frames", file=sys.stderr)
        return 1

    started = _parse_sse_chunk(frames[0])
    if started["event"] != PipelineEventType.stage_started.value:
        print(f"FAIL first SSE event: {started}", file=sys.stderr)
        return 1

    data = started["data"]
    if data.get("pipeline_run_id") != pipeline_run_id:
        print(f"FAIL pipeline_run_id in SSE data: {data}", file=sys.stderr)
        return 1
    if not data.get("timestamp"):
        print(f"FAIL missing timestamp in SSE data: {data}", file=sys.stderr)
        return 1
    if data.get("stage") != "discover":
        print(f"FAIL stage in SSE data: {data}", file=sys.stderr)
        return 1
    print("OK SSE stream replays stage_started with pipeline_run_id + timestamp")

    print("verify:sse OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
