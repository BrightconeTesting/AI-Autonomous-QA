"""Test case routes (DASHBOARD-SPEC §10)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from aqa_api.deps import get_db
from aqa_api.schemas.errors import ProblemDetail
from aqa_api.schemas.test_cases import TestCaseDetailResponse, TestCaseListResponse
from aqa_api.services import applications as app_service
from aqa_api.services import test_cases as test_case_service

router = APIRouter(prefix="/api/v1", tags=["test-cases"])


@router.get("/apps/{app_id}/test-cases", response_model=TestCaseListResponse)
def list_app_test_cases(app_id: UUID, request: Request, db: Session = Depends(get_db)):
    if app_service.get_application(db, app_id) is None:
        problem = ProblemDetail(
            type="https://autonomous-qa.dev/errors/not-found",
            title="Application Not Found",
            status=404,
            detail=f"No application exists with id {app_id}",
            instance=str(request.url.path),
        )
        return JSONResponse(status_code=404, content=problem.to_response_body())
    return test_case_service.list_test_cases(db, app_id)


@router.get("/test-cases/{testcase_id}", response_model=TestCaseDetailResponse)
def get_test_case(testcase_id: UUID, request: Request, db: Session = Depends(get_db)):
    detail = test_case_service.get_test_case(db, testcase_id)
    if detail is None:
        problem = ProblemDetail(
            type="https://autonomous-qa.dev/errors/not-found",
            title="Test Case Not Found",
            status=404,
            detail=f"No test case exists with id {testcase_id}",
            instance=str(request.url.path),
        )
        return JSONResponse(status_code=404, content=problem.to_response_body())
    return detail


@router.get("/apps/{app_id}/test-cases/export.feature")
def export_feature(app_id: UUID, request: Request, db: Session = Depends(get_db)):
    if app_service.get_application(db, app_id) is None:
        problem = ProblemDetail(
            type="https://autonomous-qa.dev/errors/not-found",
            title="Application Not Found",
            status=404,
            detail=f"No application exists with id {app_id}",
            instance=str(request.url.path),
        )
        return JSONResponse(status_code=404, content=problem.to_response_body())
    content = test_case_service.export_feature_file(db, app_id)
    if content is None:
        return PlainTextResponse("", media_type="text/plain")
    return PlainTextResponse(content, media_type="text/plain")
