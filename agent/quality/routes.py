from fastapi import APIRouter

from app.dependencies import CurrentAuth, DbSession
from quality.schemas import (
    QualityLabelCreate,
    QualityMetricRead,
    QualityOverview,
    QualityReviewCandidate,
)
from quality.service import QualityService


router = APIRouter(prefix="/quality", tags=["quality"])


@router.get("/review-sample", response_model=list[QualityReviewCandidate])
def review_sample(
    session: DbSession,
    auth: CurrentAuth,
    dimension: str,
    niche_id: str | None = None,
    market_key: str | None = None,
    limit: int = 25,
):
    return QualityService(session).review_sample(
        dimension=dimension,
        niche_id=niche_id,
        market_key=market_key,
        limit=limit,
    )


@router.post("/labels", response_model=QualityMetricRead)
def add_label(data: QualityLabelCreate, session: DbSession, auth: CurrentAuth):
    _, metric = QualityService(session).add_label(
        data,
        reviewer=auth.email or auth.user_id or "service-account",
    )
    return metric


@router.get("/metrics", response_model=list[QualityMetricRead])
def list_metrics(session: DbSession, auth: CurrentAuth, limit: int = 100):
    return QualityService(session).latest_metrics(limit=limit)


@router.get("/overview", response_model=QualityOverview)
def quality_overview(session: DbSession, auth: CurrentAuth):
    return QualityService(session).overview()
