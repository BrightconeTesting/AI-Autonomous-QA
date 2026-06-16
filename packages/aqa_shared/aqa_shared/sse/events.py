"""Pipeline SSE event schemas (SPEC §16.7, Day 14)."""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class PipelineEventType(str, Enum):
    stage_started = "stage_started"
    stage_progress = "stage_progress"
    stage_completed = "stage_completed"
    stage_failed = "stage_failed"
    pipeline_completed = "pipeline_completed"


TERMINAL_EVENT_TYPES = frozenset(
    {
        PipelineEventType.stage_failed,
        PipelineEventType.pipeline_completed,
    }
)


class PipelineSseEvent(BaseModel):
    id: str
    event: PipelineEventType
    pipeline_run_id: UUID
    timestamp: datetime
    data: dict[str, Any] = Field(default_factory=dict)

    def to_sse_frame(self) -> str:
        payload = {
            "pipeline_run_id": str(self.pipeline_run_id),
            "timestamp": self.timestamp.isoformat(),
            **self.data,
        }
        lines = [f"id: {self.id}", f"event: {self.event.value}", f"data: {json.dumps(payload)}"]
        return "\n".join(lines) + "\n\n"

    @classmethod
    def from_stored(cls, raw: str | bytes | dict[str, Any]) -> PipelineSseEvent:
        if isinstance(raw, (str, bytes)):
            parsed = json.loads(raw)
        else:
            parsed = raw
        return cls.model_validate(parsed)
