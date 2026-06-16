"""Pipeline run status routes (Day 13–14)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from aqa_api.config import settings
from aqa_api.deps import get_db
from aqa_api.schemas.errors import ProblemDetail
from aqa_api.schemas.pipeline_runs import PipelineRunResponse
from aqa_api.services import pipeline_runs as pipeline_service
from aqa_api.services.sse import stream_pipeline_events

router = APIRouter(prefix="/api/v1", tags=["pipeline-runs"])


@router.get("/pipeline-runs/{pipeline_run_id}", response_model=PipelineRunResponse)
def get_pipeline_run(
    pipeline_run_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    run = pipeline_service.get_pipeline_run(db, pipeline_run_id)
    if run is None:
        problem = ProblemDetail(
            type="https://autonomous-qa.dev/errors/not-found",
            title="Pipeline Run Not Found",
            status=404,
            detail=f"No pipeline run exists with id {pipeline_run_id}",
            instance=str(request.url.path),
        )
        return JSONResponse(status_code=404, content=problem.to_response_body())
    return pipeline_service.to_pipeline_run_response(run)


@router.get("/pipeline-runs/{pipeline_run_id}/stream")
def stream_pipeline_run(
    pipeline_run_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    run = pipeline_service.get_pipeline_run(db, pipeline_run_id)
    if run is None:
        problem = ProblemDetail(
            type="https://autonomous-qa.dev/errors/not-found",
            title="Pipeline Run Not Found",
            status=404,
            detail=f"No pipeline run exists with id {pipeline_run_id}",
            instance=str(request.url.path),
        )
        return JSONResponse(status_code=404, content=problem.to_response_body())

    return StreamingResponse(
        stream_pipeline_events(
            str(pipeline_run_id),
            last_event_id=last_event_id,
            redis_url=settings.redis_url,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
