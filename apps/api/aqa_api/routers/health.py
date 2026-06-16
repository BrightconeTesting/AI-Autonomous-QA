"""Health check route."""

import os

import redis
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from aqa_api.config import settings
from aqa_shared.db.session import check_db_connection

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    os.environ.setdefault("DATABASE_URL", settings.database_url)
    db_ok = check_db_connection()
    redis_ok = False
    try:
        client = redis.from_url(settings.redis_url, socket_connect_timeout=3)
        redis_ok = client.ping()
        client.close()
    except Exception:
        redis_ok = False

    healthy = db_ok and redis_ok
    body = {
        "status": "ok" if healthy else "error",
        "db": "ok" if db_ok else "error",
        "redis": "ok" if redis_ok else "error",
        "version": settings.api_version,
    }
    return JSONResponse(status_code=200 if healthy else 503, content=body)
