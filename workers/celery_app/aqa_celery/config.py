import os
from pathlib import Path

from dotenv import load_dotenv

from aqa_celery.task_names import TASK_ROUTES

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

broker_url = os.getenv("CELERY_BROKER_URL") or os.getenv(
    "REDIS_URL", "redis://localhost:6379/0"
)
result_backend = os.getenv("CELERY_RESULT_BACKEND", broker_url)

task_serializer = "json"
accept_content = ["json"]
result_serializer = "json"
timezone = "UTC"
enable_utc = True

task_acks_late = True
task_default_retry_delay = 60
task_routes = TASK_ROUTES
task_default_max_retries = 3

task_annotations = {
    "*": {
        "autoretry_for": (Exception,),
        "retry_backoff": True,
        "retry_backoff_max": 600,
        "retry_jitter": True,
    }
}
