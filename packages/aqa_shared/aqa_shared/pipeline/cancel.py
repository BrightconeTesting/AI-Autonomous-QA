"""Redis-backed pipeline cancellation flags."""

from __future__ import annotations

import os

import redis

CANCEL_TTL_SECONDS = 86_400


def _redis_url(redis_url: str | None = None) -> str:
    return redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379")


def _cancel_key(pipeline_run_id: str) -> str:
    return f"aqa:cancel:pipeline:{pipeline_run_id}"


def set_pipeline_cancelled(pipeline_run_id: str, *, redis_url: str | None = None) -> None:
    client = redis.from_url(_redis_url(redis_url))
    try:
        client.set(_cancel_key(pipeline_run_id), "1", ex=CANCEL_TTL_SECONDS)
    finally:
        client.close()


def is_pipeline_cancelled(pipeline_run_id: str, *, redis_url: str | None = None) -> bool:
    client = redis.from_url(_redis_url(redis_url))
    try:
        return bool(client.get(_cancel_key(pipeline_run_id)))
    finally:
        client.close()


def clear_pipeline_cancelled(pipeline_run_id: str, *, redis_url: str | None = None) -> None:
    client = redis.from_url(_redis_url(redis_url))
    try:
        client.delete(_cancel_key(pipeline_run_id))
    finally:
        client.close()
