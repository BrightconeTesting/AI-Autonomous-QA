"""Dashboard aggregate metrics."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from aqa_api.deps import get_db
from aqa_api.schemas.dashboard import DashboardSummaryResponse
from aqa_api.services import dashboard as dashboard_service

router = APIRouter(prefix="/api/v1", tags=["dashboard"])


@router.get("/dashboard/summary", response_model=DashboardSummaryResponse)
def dashboard_summary(db: Session = Depends(get_db)):
    return dashboard_service.get_dashboard_summary(db)
