from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from business_facts.repository import BusinessFactRepository, fact_value
from db.models import (
    BusinessModel,
    AudienceRunModel,
    BusinessFactModel,
    FactClaimModel,
    BusinessPublicationModel,
    NicheModel,
    QualityLabelModel,
    QualityMetricSnapshotModel,
    QueueJobModel,
    SourceItemModel,
    SourceObservationModel,
    ValidationResultModel,
)
from publication.policy import PublicationPolicyService
from quality.fact_policy import FactQualityPolicyService
from quality.repository import QualityRepository, QualityScope
from quality.schemas import (
    QualityLabelCreate,
    QualityMetricRead,
    QualityOverview,
    QualityReviewCandidate,
)
from shared.utils import utcnow


SIGNAL_FACT_KEYS = {
    "website_unavailable": "website_status",
    "reviews_under_15": "google_review_count",
    "no_quote_flow": "quote_or_booking_form_present",
    "no_contact_form": "contact_form_present",
}


class QualityService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = QualityRepository(session)

    def review_sample(
        self,
        *,
        dimension: str,
        niche_id: str | None = None,
        market_key: str | None = None,
        limit: int = 25,
    ) -> list[QualityReviewCandidate]:
        statement = (
            select(BusinessPublicationModel, BusinessModel, NicheModel)
            .join(BusinessModel, BusinessModel.id == BusinessPublicationModel.business_id)
            .join(NicheModel, NicheModel.id == BusinessPublicationModel.niche_id)
            .where(
                ~select(QualityLabelModel.id)
                .where(
                    QualityLabelModel.business_id == BusinessModel.id,
                    QualityLabelModel.dimension == dimension,
                )
                .exists()
            )
        )
        if niche_id:
            statement = statement.where(BusinessPublicationModel.niche_id == niche_id)
        if market_key:
            statement = statement.where(BusinessPublicationModel.market_key == market_key)
        rows = self.session.execute(statement.order_by(func.random()).limit(min(limit, 100))).all()
        business_ids = [business.id for _, business, _ in rows]
        facts = BusinessFactRepository(self.session).map_for_businesses(business_ids)
        observations: dict[str, list[SourceObservationModel]] = defaultdict(list)
        if business_ids:
            for observation in self.session.scalars(
                select(SourceObservationModel)
                .where(SourceObservationModel.business_id.in_(business_ids))
                .order_by(SourceObservationModel.observed_at.desc())
            ):
                observations[observation.business_id].append(observation)
        return [
            QualityReviewCandidate(
                business_id=business.id,
                display_name=business.display_name,
                address=business.address,
                phone=business.phone,
                website_url=business.website_url,
                dimension=dimension,
                predicted=self._predicted(
                    business.id,
                    dimension,
                    facts.get(business.id, {}),
                ),
                source=(observations[business.id][0].source if observations[business.id] else None),
                niche_id=niche.id,
                niche_label=niche.label,
                market_key=publication.market_key,
                publication_status=publication.status,
                publication_reasons=publication.reasons,
                evidence_urls=[
                    observation.source_url
                    for observation in observations[business.id]
                    if observation.source_url
                ][:5],
            )
            for publication, business, niche in rows
        ]

    def add_label(self, data: QualityLabelCreate, *, reviewer: str):
        scope = QualityScope(
            dimension=data.dimension,
            source=data.source,
            niche_id=data.niche_id,
            market_key=data.market_key,
            validator_version=data.validator_version,
        )
        label = self.repository.add_label(
            business_id=data.business_id,
            scope=scope,
            expected=data.expected,
            predicted=data.predicted,
            reviewer=reviewer,
            reviewed_at=utcnow(),
            evidence=data.evidence,
            notes=data.notes,
        )
        metric = self.repository.calculate(scope)
        FactQualityPolicyService(self.session).reevaluate_dimension(data.dimension)
        self._reevaluate_scope(scope)
        return label, metric

    def latest_metrics(self, *, limit: int = 100) -> list[QualityMetricSnapshotModel]:
        return list(
            self.session.scalars(
                select(QualityMetricSnapshotModel)
                .order_by(QualityMetricSnapshotModel.calculated_at.desc())
                .limit(min(limit, 500))
            )
        )

    def overview(self) -> QualityOverview:
        now = utcnow()
        metrics = list(
            self.session.scalars(
                select(QualityMetricSnapshotModel)
                .where(
                    QualityMetricSnapshotModel.source.is_(None),
                    QualityMetricSnapshotModel.niche_id.is_(None),
                    QualityMetricSnapshotModel.market_key.is_(None),
                )
                .order_by(QualityMetricSnapshotModel.calculated_at.desc())
            )
        )
        latest_metrics = {}
        for metric in metrics:
            latest_metrics.setdefault(
                metric.dimension,
                QualityMetricRead.model_validate(metric),
            )
        return QualityOverview(
            businesses=self._count(BusinessModel),
            source_observations=self._count(SourceObservationModel),
            fact_claims=self._count(FactClaimModel),
            facts_by_resolution=self._group_counts(
                BusinessFactModel,
                BusinessFactModel.resolution_state,
            ),
            facts_by_quality=self._group_counts(
                BusinessFactModel,
                BusinessFactModel.quality_state,
            ),
            validations_by_status=self._group_counts(
                ValidationResultModel,
                ValidationResultModel.status,
            ),
            publications_by_status=self._group_counts(
                BusinessPublicationModel,
                BusinessPublicationModel.status,
            ),
            source_items_by_state=self._group_counts(
                SourceItemModel,
                SourceItemModel.state,
            ),
            audience_runs_by_state=self._group_counts(
                AudienceRunModel,
                AudienceRunModel.state,
            ),
            queue_jobs_by_status=self._group_counts(
                QueueJobModel,
                QueueJobModel.status,
            ),
            expired_facts=int(
                self.session.scalar(
                    select(func.count())
                    .select_from(BusinessFactModel)
                    .where(
                        BusinessFactModel.expires_at.is_not(None),
                        BusinessFactModel.expires_at < now,
                    )
                )
                or 0
            ),
            expired_publications=int(
                self.session.scalar(
                    select(func.count())
                    .select_from(BusinessPublicationModel)
                    .where(
                        BusinessPublicationModel.expires_at.is_not(None),
                        BusinessPublicationModel.expires_at < now,
                    )
                )
                or 0
            ),
            latest_global_metrics=latest_metrics,
        )

    def _count(self, model) -> int:
        return int(
            self.session.scalar(select(func.count()).select_from(model)) or 0
        )

    def _group_counts(self, model, column) -> dict[str, int]:
        return {
            str(value): int(count)
            for value, count in self.session.execute(
                select(column, func.count()).select_from(model).group_by(column)
            )
        }

    def _predicted(self, business_id: str, dimension: str, facts: dict):
        fact_key = SIGNAL_FACT_KEYS.get(dimension)
        if fact_key:
            value = fact_value(facts.get(fact_key))
            if dimension == "website_unavailable":
                return value in {"missing", "unavailable", "parked"}
            if dimension == "reviews_under_15":
                return value < 15 if isinstance(value, (int, float)) else None
            return not value if isinstance(value, bool) else None
        validation = self.session.scalar(
            select(ValidationResultModel)
            .where(
                ValidationResultModel.business_id == business_id,
                ValidationResultModel.validation_type == dimension,
            )
            .order_by(ValidationResultModel.observed_at.desc())
            .limit(1)
        )
        return validation.status == "passed" if validation else None

    def _reevaluate_scope(self, scope: QualityScope) -> None:
        statement = select(BusinessPublicationModel)
        if scope.niche_id:
            statement = statement.where(BusinessPublicationModel.niche_id == scope.niche_id)
        if scope.market_key:
            statement = statement.where(BusinessPublicationModel.market_key == scope.market_key)
        publications = list(self.session.scalars(statement))
        for publication in publications:
            PublicationPolicyService(self.session).evaluate(
                business_id=publication.business_id,
                niche_id=publication.niche_id,
                market_key=publication.market_key,
                source=scope.source,
            )
