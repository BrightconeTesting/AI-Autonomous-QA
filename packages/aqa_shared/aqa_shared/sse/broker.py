"""Redis-backed pipeline SSE event log + pub/sub (Day 14)."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import redis

from aqa_shared.sse.events import PipelineEventType, PipelineSseEvent, TERMINAL_EVENT_TYPES

EVENT_TTL_SECONDS = 86_400


def _redis_url(redis_url: str | None = None) -> str:
    return redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379")


def _list_key(pipeline_run_id: str) -> str:
    return f"aqa:sse:pipeline:{pipeline_run_id}:events"


def _seq_key(pipeline_run_id: str) -> str:
    return f"aqa:sse:pipeline:{pipeline_run_id}:seq"


def _channel(pipeline_run_id: str) -> str:
    return f"aqa:sse:pipeline:{pipeline_run_id}:live"


def publish_pipeline_event(
    pipeline_run_id: str,
    event_type: PipelineEventType | str,
    data: dict[str, Any] | None = None,
    *,
    redis_url: str | None = None,
) -> PipelineSseEvent:
    """Append event to Redis log and notify live subscribers."""
    resolved_type = (
        event_type if isinstance(event_type, PipelineEventType) else PipelineEventType(event_type)
    )
    client = redis.from_url(_redis_url(redis_url))
    try:
        event_id = str(client.incr(_seq_key(pipeline_run_id)))
        event = PipelineSseEvent(
            id=event_id,
            event=resolved_type,
            pipeline_run_id=UUID(pipeline_run_id),
            timestamp=datetime.now(timezone.utc),
            data=data or {},
        )
        payload = event.model_dump(mode="json")
        encoded = json.dumps(payload)
        list_key = _list_key(pipeline_run_id)
        client.rpush(list_key, encoded)
        client.expire(list_key, EVENT_TTL_SECONDS)
        client.expire(_seq_key(pipeline_run_id), EVENT_TTL_SECONDS)
        client.publish(_channel(pipeline_run_id), encoded)
        return event
    finally:
        client.close()


def list_pipeline_events(
    pipeline_run_id: str,
    *,
    after_event_id: str | None = None,
    redis_url: str | None = None,
) -> list[PipelineSseEvent]:
    client = redis.from_url(_redis_url(redis_url))
    try:
        raw_items = client.lrange(_list_key(pipeline_run_id), 0, -1)
    finally:
        client.close()

    events = [PipelineSseEvent.from_stored(item) for item in raw_items]
    if after_event_id is None:
        return events
    return [event for event in events if int(event.id) > int(after_event_id)]


def _iter_new_events(
    pipeline_run_id: str,
    *,
    after_event_id: str | None,
    last_seen: str | None,
    redis_url: str,
) -> tuple[list[PipelineSseEvent], str | None, bool]:
    events: list[PipelineSseEvent] = []
    seen = last_seen
    for event in list_pipeline_events(
        pipeline_run_id, after_event_id=after_event_id, redis_url=redis_url
    ):
        if seen is not None and int(event.id) <= int(seen):
            continue
        seen = event.id
        events.append(event)
        if event.event in TERMINAL_EVENT_TYPES:
            return events, seen, True
    return events, seen, False


def subscribe_pipeline_events(
    pipeline_run_id: str,
    *,
    after_event_id: str | None = None,
    redis_url: str | None = None,
    poll_timeout: float = 1.0,
) -> Iterator[PipelineSseEvent]:
    """Replay stored events then block on pub/sub until a terminal event."""
    url = _redis_url(redis_url)
    last_seen = after_event_id

    batch, last_seen, terminal = _iter_new_events(
        pipeline_run_id, after_event_id=after_event_id, last_seen=last_seen, redis_url=url
    )
    for event in batch:
        yield event
    if terminal:
        return

    batch, last_seen, terminal = _iter_new_events(
        pipeline_run_id, after_event_id=last_seen, last_seen=last_seen, redis_url=url
    )
    for event in batch:
        yield event
    if terminal:
        return

    client = redis.from_url(url)
    pubsub = client.pubsub()
    try:
        pubsub.subscribe(_channel(pipeline_run_id))
        while True:
            message = pubsub.get_message(ignore_subscribe_messages=True, timeout=poll_timeout)
            if message is None or message.get("type") != "message":
                continue
            event = PipelineSseEvent.from_stored(message["data"])
            if last_seen is not None and int(event.id) <= int(last_seen):
                continue
            last_seen = event.id
            yield event
            if event.event in TERMINAL_EVENT_TYPES:
                return
    finally:
        pubsub.close()
        client.close()
