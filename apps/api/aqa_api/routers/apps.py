"""Application registration and listing (SPEC §16.2, Day 11–12)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from aqa_api.config import settings
from aqa_api.deps import get_db
from aqa_api.schemas.apps import ApplicationListResponse, ApplicationResponse, CreateApplicationRequest
from aqa_api.schemas.appmap import AppMapResponse
from aqa_api.schemas.discovery_summary import DiscoverySummaryResponse
from aqa_api.schemas.appmap_approval import (
    AppMapApprovalResponse,
    AppMapApprovalStatusResponse,
    AppMapRejectRequest,
)
from aqa_api.schemas.errors import ProblemDetail
from aqa_api.schemas.generate_tests import GenerateTestsRequest, GenerateTestsResponse
from aqa_api.schemas.pipeline_runs import ActivePipelineResponse, DiscoverRequest, DiscoverResponse
from aqa_api.services import appmap as appmap_service
from aqa_api.services import discovery_summary as discovery_summary_service
from aqa_api.services import appmap_approval as appmap_approval_service
from aqa_api.services import applications as app_service
from aqa_api.services import pipeline_runs as pipeline_service
from aqa_api.services import test_generation as test_generation_service
from aqa_api.services.pipeline_runs import ActivePipelineConflictError
from aqa_api.services.test_generation import AppMapApprovalRequiredError, AppMapPreconditionError
from aqa_shared.crypto.auth_config import EncryptionKeyError
from aqa_shared.security.url_validator import UrlSecurityError

router = APIRouter(prefix="/api/v1", tags=["applications"])


def _problem_response(
    request: Request,
    *,
    status: int,
    title: str,
    detail: str,
    problem_type: str = "https://autonomous-qa.dev/errors/validation",
) -> JSONResponse:
    problem = ProblemDetail(
        type=problem_type,
        title=title,
        status=status,
        detail=detail,
        instance=str(request.url.path),
    )
    return JSONResponse(status_code=status, content=problem.to_response_body())


@router.post("/apps", status_code=201, response_model=ApplicationResponse)
def create_application(
    body: CreateApplicationRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        app = app_service.create_application(db, body)
    except UrlSecurityError as exc:
        return _problem_response(request, status=400, title="Validation Error", detail=str(exc))
    except EncryptionKeyError as exc:
        return _problem_response(request, status=400, title="Validation Error", detail=str(exc))
    except Exception as exc:
        if settings.is_development:
            return _problem_response(
                request,
                status=500,
                title="Internal Server Error",
                detail=str(exc),
                problem_type="https://autonomous-qa.dev/errors/internal",
            )
        raise
    return app_service.to_application_response(app)


@router.get("/apps", response_model=ApplicationListResponse)
def list_applications(db: Session = Depends(get_db)):
    apps = app_service.list_applications(db)
    items = [app_service.to_application_response(a) for a in apps]
    return ApplicationListResponse(items=items, total=len(items))


@router.get("/apps/{app_id}", response_model=ApplicationResponse)
def get_application(app_id: UUID, request: Request, db: Session = Depends(get_db)):
    app = app_service.get_application(db, app_id)
    if app is None:
        problem = ProblemDetail(
            type="https://autonomous-qa.dev/errors/not-found",
            title="Application Not Found",
            status=404,
            detail=f"No application exists with id {app_id}",
            instance=str(request.url.path),
        )
        return JSONResponse(status_code=404, content=problem.to_response_body())
    return app_service.to_application_response(app)


@router.delete("/apps/{app_id}", status_code=204)
def delete_application(app_id: UUID, request: Request, db: Session = Depends(get_db)):
    try:
        deleted = app_service.delete_application(db, app_id)
    except ActivePipelineConflictError as exc:
        problem = ProblemDetail(
            type="https://autonomous-qa.dev/errors/conflict",
            title="Pipeline Already Running",
            status=409,
            detail="Stop the active pipeline before deleting this application",
            instance=str(request.url.path),
            active_pipeline_run_id=str(exc.active_run_id),
        )
        return JSONResponse(status_code=409, content=problem.to_response_body())
    if not deleted:
        problem = ProblemDetail(
            type="https://autonomous-qa.dev/errors/not-found",
            title="Application Not Found",
            status=404,
            detail=f"No application exists with id {app_id}",
            instance=str(request.url.path),
        )
        return JSONResponse(status_code=404, content=problem.to_response_body())
    return None


@router.get("/apps/{app_id}/active-pipeline", response_model=ActivePipelineResponse)
def get_active_pipeline(app_id: UUID, request: Request, db: Session = Depends(get_db)):
    app = app_service.get_application(db, app_id)
    if app is None:
        problem = ProblemDetail(
            type="https://autonomous-qa.dev/errors/not-found",
            title="Application Not Found",
            status=404,
            detail=f"No application exists with id {app_id}",
            instance=str(request.url.path),
        )
        return JSONResponse(status_code=404, content=problem.to_response_body())
    active = pipeline_service.get_active_pipeline_for_app(db, app_id)
    if active is None:
        return ActivePipelineResponse(pipeline_run=None)
    return ActivePipelineResponse(pipeline_run=pipeline_service.to_pipeline_run_response(active))


@router.get("/apps/{app_id}/appmap", response_model=AppMapResponse)
def get_appmap(app_id: UUID, request: Request, db: Session = Depends(get_db)):
    appmap = appmap_service.get_appmap(db, app_id)
    if appmap is None:
        problem = ProblemDetail(
            type="https://autonomous-qa.dev/errors/not-found",
            title="Application Not Found",
            status=404,
            detail=f"No application exists with id {app_id}",
            instance=str(request.url.path),
        )
        return JSONResponse(status_code=404, content=problem.to_response_body())
    return appmap


@router.get("/apps/{app_id}/discovery-summary", response_model=DiscoverySummaryResponse)
def get_discovery_summary(app_id: UUID, request: Request, db: Session = Depends(get_db)):
    summary = discovery_summary_service.get_discovery_summary(db, app_id)
    if summary is None:
        problem = ProblemDetail(
            type="https://autonomous-qa.dev/errors/not-found",
            title="Application Not Found",
            status=404,
            detail=f"No application exists with id {app_id}",
            instance=str(request.url.path),
        )
        return JSONResponse(status_code=404, content=problem.to_response_body())
    return summary


@router.get("/apps/{app_id}/appmap/approval", response_model=AppMapApprovalStatusResponse)
def get_appmap_approval(app_id: UUID, request: Request, db: Session = Depends(get_db)):
    app = app_service.get_application(db, app_id)
    if app is None:
        problem = ProblemDetail(
            type="https://autonomous-qa.dev/errors/not-found",
            title="Application Not Found",
            status=404,
            detail=f"No application exists with id {app_id}",
            instance=str(request.url.path),
        )
        return JSONResponse(status_code=404, content=problem.to_response_body())
    return appmap_approval_service.get_approval_status(db, app_id)


@router.post("/apps/{app_id}/appmap/approve", response_model=AppMapApprovalResponse)
def approve_appmap(app_id: UUID, request: Request, db: Session = Depends(get_db)):
    app = app_service.get_application(db, app_id)
    if app is None:
        problem = ProblemDetail(
            type="https://autonomous-qa.dev/errors/not-found",
            title="Application Not Found",
            status=404,
            detail=f"No application exists with id {app_id}",
            instance=str(request.url.path),
        )
        return JSONResponse(status_code=404, content=problem.to_response_body())
    try:
        run = appmap_approval_service.approve_appmap(db, app_id)
    except appmap_approval_service.AppMapApprovalError as exc:
        return _problem_response(
            request,
            status=422,
            title="AppMap Approval Error",
            detail=exc.detail,
            problem_type="https://autonomous-qa.dev/errors/precondition",
        )
    status = appmap_approval_service.get_approval_status(db, app_id)
    assert run.id == status.pipeline_run_id
    return AppMapApprovalResponse(
        application_id=app_id,
        pipeline_run_id=run.id,
        status=status.status,
        approved_at=status.approved_at,
        rejection_reason=status.rejection_reason,
    )


@router.post("/apps/{app_id}/appmap/reject", response_model=AppMapApprovalResponse)
def reject_appmap(
    app_id: UUID,
    request: Request,
    body: AppMapRejectRequest | None = None,
    db: Session = Depends(get_db),
):
    app = app_service.get_application(db, app_id)
    if app is None:
        problem = ProblemDetail(
            type="https://autonomous-qa.dev/errors/not-found",
            title="Application Not Found",
            status=404,
            detail=f"No application exists with id {app_id}",
            instance=str(request.url.path),
        )
        return JSONResponse(status_code=404, content=problem.to_response_body())
    try:
        run = appmap_approval_service.reject_appmap(
            db, app_id, reason=(body.reason if body else "")
        )
    except appmap_approval_service.AppMapApprovalError as exc:
        return _problem_response(
            request,
            status=422,
            title="AppMap Approval Error",
            detail=exc.detail,
            problem_type="https://autonomous-qa.dev/errors/precondition",
        )
    status = appmap_approval_service.get_approval_status(db, app_id)
    return AppMapApprovalResponse(
        application_id=app_id,
        pipeline_run_id=run.id,
        status=status.status,
        approved_at=status.approved_at,
        rejection_reason=status.rejection_reason,
    )


@router.post("/apps/{app_id}/discover", status_code=202, response_model=DiscoverResponse)
def start_discovery(
    app_id: UUID,
    request: Request,
    body: DiscoverRequest | None = None,
    db: Session = Depends(get_db),
):
    app = app_service.get_application(db, app_id)
    if app is None:
        problem = ProblemDetail(
            type="https://autonomous-qa.dev/errors/not-found",
            title="Application Not Found",
            status=404,
            detail=f"No application exists with id {app_id}",
            instance=str(request.url.path),
        )
        return JSONResponse(status_code=404, content=problem.to_response_body())

    discover_body = body or DiscoverRequest()
    try:
        run = pipeline_service.start_discovery(db, app_id, discover_body)
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
    return pipeline_service.to_discover_response(run)


@router.post(
    "/apps/{app_id}/generate-tests",
    status_code=202,
    response_model=GenerateTestsResponse,
)
def start_generate_tests(
    app_id: UUID,
    request: Request,
    body: GenerateTestsRequest | None = None,
    db: Session = Depends(get_db),
):
    app = app_service.get_application(db, app_id)
    if app is None:
        problem = ProblemDetail(
            type="https://autonomous-qa.dev/errors/not-found",
            title="Application Not Found",
            status=404,
            detail=f"No application exists with id {app_id}",
            instance=str(request.url.path),
        )
        return JSONResponse(status_code=404, content=problem.to_response_body())

    generate_body = body or GenerateTestsRequest()
    try:
        run = test_generation_service.start_generate_tests(db, app_id, generate_body)
    except AppMapPreconditionError as exc:
        return _problem_response(
            request,
            status=422,
            title="AppMap Required",
            detail=exc.detail,
            problem_type="https://autonomous-qa.dev/errors/precondition",
        )
    except AppMapApprovalRequiredError as exc:
        return _problem_response(
            request,
            status=422,
            title="AppMap Approval Required",
            detail=exc.detail,
            problem_type="https://autonomous-qa.dev/errors/precondition",
        )
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
    return test_generation_service.to_generate_tests_response(run)
