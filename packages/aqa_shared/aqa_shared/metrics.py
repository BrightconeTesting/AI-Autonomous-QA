"""Prometheus metrics shared across API and workers (SPEC §22.2)."""

from prometheus_client import Histogram

aqa_crawl_time_seconds = Histogram(
    "aqa_crawl_time_seconds",
    "Discovery crawl wall-clock duration in seconds",
    buckets=(1, 5, 10, 30, 60, 120, 300, 600),
)
