#!/usr/bin/env python3
"""Verify aqa_shared imports and Celery constants."""

from aqa_shared import (
    CELERY_TASK_DISCOVER,
    CELERY_TASK_ROUTES,
    PipelineStage,
    PipelineStatus,
    QUEUE_DISCOVER,
    QUEUE_NAMES,
)
from aqa_shared.types.agent import AgentContext

ctx = AgentContext(
    pipelineRunId="00000000-0000-0000-0000-000000000001",
    applicationId="00000000-0000-0000-0000-000000000002",
    pluginId="ui",
    mode="ui",
    tokenBudgetRemaining=8000,
)

print("verify:shared OK")
print(
    {
        "queue": QUEUE_DISCOVER,
        "celeryTask": CELERY_TASK_DISCOVER,
        "celeryRoute": CELERY_TASK_ROUTES[CELERY_TASK_DISCOVER],
        "queues": len(QUEUE_NAMES),
        "status": PipelineStatus.pending.value,
        "stage": PipelineStage.discover.value,
        "ctx": ctx.pipeline_run_id,
    }
)
