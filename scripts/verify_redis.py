#!/usr/bin/env python3
"""Verify local Redis connectivity."""

import os
import sys

import redis
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

url = os.getenv("REDIS_URL", "redis://localhost:6379")

try:
    client = redis.from_url(url, socket_connect_timeout=3)
    pong = client.ping()
    client.close()
    print("verify:redis OK", {"url": url, "ping": pong})
except Exception as exc:
    print("verify:redis FAILED", exc, file=sys.stderr)
    sys.exit(1)
