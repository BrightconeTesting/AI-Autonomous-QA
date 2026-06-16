"""Celery queue names (Redis broker routing keys)."""

QUEUE_DISCOVER = "discover"
QUEUE_DESIGN = "design"
QUEUE_GENERATE_SCRIPTS = "generate-scripts"
QUEUE_EXECUTE = "execute"
QUEUE_REPORT = "report"
QUEUE_ANALYZE = "analyze"

QUEUE_NAMES: tuple[str, ...] = (
    QUEUE_DISCOVER,
    QUEUE_DESIGN,
    QUEUE_GENERATE_SCRIPTS,
    QUEUE_EXECUTE,
    QUEUE_REPORT,
    QUEUE_ANALYZE,
)
