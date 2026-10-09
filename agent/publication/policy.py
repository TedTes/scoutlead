from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from db.models import BusinessPublicationModel, QualityMetricSnapshotModel
from pipeline_outbox.repository import PipelineOutboxRepository
from publication.repository import PublicationRepository, ValidationRepository
from shared.utils import utcnow


POLICY_VERSION = 1
REQUIRED_VALIDATIONS = {
    "identity": 90,
    "business_identity": 85,
    "trade": 90,
    "location": 85,
}
QUALITY_THRESHOLDS = {
    "identity": 0.98,
    "business_identity": 0.98,
    "trade": 0.98,
    "location": 0.98,
}
MINIMUM_QUALITY_SAMPLE = 30
MINIMUM_PRECISION_LOWER_BOUND = 0.85


class PublicationPolicyService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.validations = ValidationRepository(session)
        self.publications = PublicationRepository(session)

    def evaluate(
        self,
        *,
        business_id: str,
        niche_id: str,
        market_key: str,
        source: str | None,
        commit: bool = True,
    ) -> BusinessPublicationModel:
        now = utcnow()
        previous = self.session.scalar(
            select(BusinessPublicationModel)
            .where(
                BusinessPublicationModel.business_id == business_id,
                BusinessPublicationModel.niche_id == niche_id,
                BusinessPublicationModel.market_key == market_key,
            )
            .limit(1)
        )
        previous_status = previous.status if previous is not None else None
        current = self.validations.latest_current(
            business_id,
            niche_id=niche_id,
            market_key=market_key,
            now=now,
        )
        reasons: list[dict] = []
        status = "published"
        expiries = []
        for dimension, minimum_confidence in REQUIRED_VALIDATIONS.items():
            result = current.get(dimension)
            if result is None:
                status = "staged"
                reasons.append({"code": "validation_missing", "dimension": dimension})
                continue
            expiries.append(result.expires_at)
            if result.status == "failed":
                status = "quarantined"
                reasons.append({"code": "validation_failed", "dimension": dimension})
            elif result.status != "passed" or result.confidence < minimum_confidence:
                if status != "quarantined":
                    status = "staged"
                reasons.append(
                    {
                        "code": "validation_insufficient",
                        "dimension": dimension,
                        "confidence": result.confidence,
                    }
                )
            metric = self._quality_metric(
                dimension=dimension,
                source=source,
                niche_id=niche_id,
                market_key=market_key,
            )
            if metric is None or metric.sample_size < MINIMUM_QUALITY_SAMPLE:
                if status == "published":
                    status = "staged"
                reasons.append({"code": "quality_sample_insufficient", "dimension": dimension})
            elif (
                metric.precision is None
                or metric.precision < QUALITY_THRESHOLDS[dimension]
                or metric.precision_lower_bound is None
                or metric.precision_lower_bound < MINIMUM_PRECISION_LOWER_BOUND
            ):
                status = "quarantined"
                reasons.append(
                    {
                        "code": "quality_threshold_failed",
                        "dimension": dimension,
                        "precision": metric.precision,
                        "precision_lower_bound": metric.precision_lower_bound,
                    }
                )
        if status == "published":
            reasons.append({"code": "policy_passed", "policy_version": POLICY_VERSION})
        publication = self.publications.upsert(
            business_id=business_id,
            niche_id=niche_id,
            market_key=market_key,
            status=status,
            policy_version=POLICY_VERSION,
            reasons=reasons,
            evaluated_at=now,
            expires_at=min(expiries) if expiries else None,
            commit=False,
        )
        if previous_status != status:
            PipelineOutboxRepository(self.session).emit(
                topic="business.publication_changed",
                aggregate_type="business_publication",
                aggregate_id=publication.id,
                payload={
                    "publication_id": publication.id,
                    "business_id": business_id,
                    "niche_id": niche_id,
                    "market_key": market_key,
                    "previous_status": previous_status,
                    "status": status,
                },
                idempotency_key=(
                    f"publication:{publication.id}:{POLICY_VERSION}:"
                    f"{status}:{now.isoformat()}"
                ),
            )
        if commit:
            self.session.commit()
            self.session.refresh(publication)
        return publication

    def _quality_metric(self, *, dimension, source, niche_id, market_key):
        candidates = list(
            self.session.scalars(
                select(QualityMetricSnapshotModel)
                .where(
                    QualityMetricSnapshotModel.dimension == dimension,
                    or_(
                        QualityMetricSnapshotModel.source == source,
                        QualityMetricSnapshotModel.source.is_(None),
                    ),
                    or_(
                        QualityMetricSnapshotModel.niche_id == niche_id,
                        QualityMetricSnapshotModel.niche_id.is_(None),
                    ),
                    or_(
                        QualityMetricSnapshotModel.market_key == market_key,
                        QualityMetricSnapshotModel.market_key.is_(None),
                    ),
                )
                .order_by(QualityMetricSnapshotModel.calculated_at.desc())
            )
        )
        if not candidates:
            return None
        candidates.sort(
            key=lambda item: (
                item.source == source,
                item.niche_id == niche_id,
                item.market_key == market_key,
                item.calculated_at,
            ),
            reverse=True,
        )
        return candidates[0]
