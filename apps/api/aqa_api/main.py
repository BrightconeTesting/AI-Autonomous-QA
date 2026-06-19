"""FastAPI orchestration API entrypoint."""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aqa_api.config import settings
from aqa_api.routers import apps, dashboard, health, metrics, pipeline_runs, queues, runs, test_cases

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)

os.environ.setdefault("DATABASE_URL", settings.database_url)
os.environ.setdefault("CELERY_BROKER_URL", settings.broker_url)
os.environ.setdefault("CELERY_RESULT_BACKEND", settings.result_backend)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        from aqa_celery.app import app as celery_app

        with celery_app.connection_or_acquire():
            pass
        logger.info("Celery client ready", extra={"broker": settings.broker_url})
    except Exception:
        logger.exception("Celery client failed to initialize")
    yield


app = FastAPI(title="Autonomous QA Platform API", version=settings.api_version, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(metrics.router)
app.include_router(queues.router)
app.include_router(apps.router)
app.include_router(dashboard.router)
app.include_router(pipeline_runs.router)
app.include_router(test_cases.router)
app.include_router(runs.router)
