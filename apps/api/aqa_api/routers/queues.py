"""Dev-only Celery queue depth via Redis LLEN."""

import redis
from fastapi import APIRouter, HTTPException

from aqa_api.config import settings
from aqa_shared.queue.names import QUEUE_NAMES

router = APIRouter(prefix="/api/v1", tags=["queues"])


@router.get("/queues/stats")
def queue_stats():
    if not settings.is_development:
        raise HTTPException(status_code=404, detail="Not found")

    try:
        client = redis.from_url(settings.redis_url, socket_connect_timeout=3)
        queues = {name: client.llen(name) for name in QUEUE_NAMES}
        client.close()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Redis unavailable") from exc

    return {
        "broker": settings.broker_url,
        "queues": queues,
    }
