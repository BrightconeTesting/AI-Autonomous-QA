"""Test runs, execute, and artifact routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy.orm import Session

from aqa_api.deps import get_db
from aqa_api.schemas.errors import ProblemDetail
from aqa_api.schemas.execute import ExecuteRequest, ExecuteResponse
from aqa_api.schemas.runs import ArtifactMetaResponse, TestRunDetailResponse, TestRunListResponse
from aqa_api.services import applications as app_service
from aqa_api.services import artifacts as artifact_service
from aqa_api.services import test_execution as execution_service
from aqa_api.services.pipeline_runs import ActivePipelineConflictError

router = APIRouter(prefix="/api/v1", tags=["runs"])


def _not_found(request: Request, title: str, detail: str) -> JSONResponse:
    problem = ProblemDetail(
        type="https://autonomous-qa.dev/errors/not-found",
        title=title,
        status=404,
        detail=detail,
        instance=str(request.url.path),
    )
    return JSONResponse(status_code=404, content=problem.to_response_body())


@router.post("/apps/{app_id}/execute", status_code=202, response_model=ExecuteResponse)
def execute_tests(
    app_id: UUID,
    request: Request,
    body: ExecuteRequest | None = None,
    db: Session = Depends(get_db),
):
    if app_service.get_application(db, app_id) is None:
        return _not_found(request, "Application Not Found", f"No application exists with id {app_id}")

    execute_body = body or ExecuteRequest()
    try:
        pipeline, test_run = execution_service.start_execute(db, app_id, execute_body)
    except execution_service.ExecutePreconditionError as exc:
        problem = ProblemDetail(
            type="https://autonomous-qa.dev/errors/precondition",
            title="Execute Precondition Failed",
            status=422,
            detail=exc.detail,
            instance=str(request.url.path),
        )
        return JSONResponse(status_code=422, content=problem.to_response_body())
    except ActivePipelineConflictError as exc:
        problem = ProblemDetail(
            type="https://autonomous-qa.dev/errors/conflict",
            title="Pipeline Already Running",
            status=409,
            detail="Application already has an active pipeline run",
            instance=str(request.url.path),
            active_pipeline_run_id=str(exc.active_run_id),
        )
        return JSONResponse(status_code=409, content=problem.to_response_body())

    return execution_service.to_execute_response(pipeline, test_run)


@router.get("/apps/{app_id}/runs", response_model=TestRunListResponse)
def list_app_runs(app_id: UUID, request: Request, db: Session = Depends(get_db)):
    if app_service.get_application(db, app_id) is None:
        return _not_found(request, "Application Not Found", f"No application exists with id {app_id}")
    return execution_service.list_runs(db, app_id)


@router.get("/runs/{run_id}", response_model=TestRunDetailResponse)
def get_run(run_id: UUID, request: Request, db: Session = Depends(get_db)):
    detail = execution_service.get_run_detail(db, run_id)
    if detail is None:
        return _not_found(request, "Run Not Found", f"No test run exists with id {run_id}")
    return detail


@router.get("/artifacts/{artifact_id}/meta", response_model=ArtifactMetaResponse)
def get_artifact_meta(artifact_id: UUID, request: Request, db: Session = Depends(get_db)):
    artifact = artifact_service.get_artifact(db, artifact_id)
    if artifact is None:
        return _not_found(request, "Artifact Not Found", f"No artifact exists with id {artifact_id}")
    return artifact_service.artifact_meta(db, artifact)


@router.get("/artifacts/{artifact_id}")
def stream_artifact(artifact_id: UUID, request: Request, db: Session = Depends(get_db)):
    artifact = artifact_service.get_artifact(db, artifact_id)
    if artifact is None:
        return _not_found(request, "Artifact Not Found", f"No artifact exists with id {artifact_id}")

    from pathlib import Path

    path = Path(artifact.path)
    if not path.is_file():
        return _not_found(request, "Artifact Not Found", f"Artifact file missing for id {artifact_id}")

    media_type = "application/octet-stream"
    if path.suffix == ".webm":
        media_type = "video/webm"
    elif path.suffix == ".mp4":
        media_type = "video/mp4"
    elif path.suffix == ".png":
        media_type = "image/png"
    elif path.suffix == ".zip":
        media_type = "application/zip"

    return FileResponse(path, media_type=media_type, filename=path.name)


@router.delete("/artifacts/{artifact_id}", status_code=204)
def delete_artifact(artifact_id: UUID, request: Request, db: Session = Depends(get_db)):
    artifact = artifact_service.get_artifact(db, artifact_id)
    if artifact is None:
        return _not_found(request, "Artifact Not Found", f"No artifact exists with id {artifact_id}")
    artifact_service.delete_artifact(db, artifact)
    return Response(status_code=204)


@router.get("/apps/{app_id}/pages/{page_id}/screenshot")
def page_screenshot(app_id: UUID, page_id: UUID, request: Request, db: Session = Depends(get_db)):
    from aqa_shared.db.models import Page

    page = db.get(Page, page_id)
    if page is None or page.app_id != app_id or not page.screenshot_path:
        return _not_found(request, "Screenshot Not Found", f"No screenshot for page {page_id}")

    from pathlib import Path

    path = Path(page.screenshot_path)
    if not path.is_file():
        return _not_found(request, "Screenshot Not Found", f"Screenshot file missing for page {page_id}")
    return FileResponse(path, media_type="image/png", filename=path.name)
