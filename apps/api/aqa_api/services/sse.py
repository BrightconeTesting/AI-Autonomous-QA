"""SSE streaming for pipeline run progress (Day 14)."""

from __future__ import annotations

from collections.abc import Iterator

from aqa_shared.sse.broker import subscribe_pipeline_events


def stream_pipeline_events(
    pipeline_run_id: str,
    *,
    last_event_id: str | None = None,
    redis_url: str,
) -> Iterator[str]:
    """Yield SSE frames for a pipeline run; replays stored events on connect."""
    for event in subscribe_pipeline_events(
        pipeline_run_id,
        after_event_id=last_event_id,
        redis_url=redis_url,
    ):
        yield event.to_sse_frame()
