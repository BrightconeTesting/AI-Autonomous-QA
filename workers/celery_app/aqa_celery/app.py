from celery import Celery

from aqa_celery import config

app = Celery("aqa")
app.config_from_object(config)
app.autodiscover_tasks(["aqa_celery.tasks"])

# Explicit imports so task modules register on worker startup.
import aqa_celery.tasks  # noqa: E402, F401
