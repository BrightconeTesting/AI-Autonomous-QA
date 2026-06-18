"""Prometheus metrics shared across API and workers (SPEC §22.2)."""

from prometheus_client import Counter, Histogram

aqa_crawl_time_seconds = Histogram(
    "aqa_crawl_time_seconds",
    "Discovery crawl wall-clock duration in seconds",
    buckets=(1, 5, 10, 30, 60, 120, 300, 600),
)

aqa_cic_states_total = Counter(
    "aqa_cic_states_total",
    "UI states discovered by CIC",
)

aqa_cic_interactions_total = Counter(
    "aqa_cic_interactions_total",
    "Safe interactions executed by CIC",
)

aqa_cic_safety_skips_total = Counter(
    "aqa_cic_safety_skips_total",
    "Interactions skipped by CIC safety classifier",
)
