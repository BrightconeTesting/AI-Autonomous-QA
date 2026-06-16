"""Prometheus metrics endpoint (SPEC §22.2)."""

import redis
from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, Gauge, generate_latest

from aqa_api.config import settings
from aqa_shared.queue.names import QUEUE_NAMES

router = APIRouter(tags=["metrics"])

aqa_queue_depth = Gauge(
    "aqa_queue_depth",
    "Celery waiting jobs per queue",
    ["queue"],
)


def _refresh_queue_depths() -> None:
    try:
        client = redis.from_url(settings.redis_url, socket_connect_timeout=3)
        for name in QUEUE_NAMES:
            aqa_queue_depth.labels(queue=name).set(client.llen(name))
        client.close()
    except Exception:
        for name in QUEUE_NAMES:
            aqa_queue_depth.labels(queue=name).set(0)


@router.get("/metrics")
def metrics():
    _refresh_queue_depths()
    return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
