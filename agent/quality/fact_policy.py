from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from db.models import (
    BusinessFactModel,
    QualityMetricSnapshotModel,
    SourceObservationModel,
)


FACT_DIMENSIONS = {
    "website_status": "website_unavailable",
    "google_review_count": "reviews_under_15",
    "quote_or_booking_form_present": "no_quote_flow",
    "contact_form_present": "no_contact_form",
}
FACT_KEYS_BY_DIMENSION = {value: key for key, value in FACT_DIMENSIONS.items()}
PRECISION_THRESHOLDS = {
    "website_unavailable": 0.95,
    "reviews_under_15": 0.98,
    "no_quote_flow": 0.90,
    "no_contact_form": 0.90,
}
MINIMUM_SAMPLE = 30
MINIMUM_PRECISION_LOWER_BOUND = 0.80
POLICY_VERSION = 1


class FactQualityPolicyService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def evaluate(
        self,
        fact: BusinessFactModel,
        *,
        commit: bool = True,
    ) -> BusinessFactModel:
        dimension = FACT_DIMENSIONS.get(fact.fact_key)
        if dimension is None:
            fact.quality_state = "published"
            fact.quality_policy_version = POLICY_VERSION
            return self._finish(fact, commit)
        if fact.resolution_state != "confirmed" or fact.confidence < 90:
            fact.quality_state = "staged"
            fact.quality_policy_version = POLICY_VERSION
            return self._finish(fact, commit)
        source = None
        if fact.source_observation_id:
            observation = self.session.get(
                SourceObservationModel,
                fact.source_observation_id,
            )
            source = observation.source if observation is not None else None
        metric = self._latest_metric(dimension, source=source)
        if metric is None or metric.sample_size < MINIMUM_SAMPLE:
            fact.quality_state = "staged"
        elif (
            metric.precision is not None
            and metric.precision >= PRECISION_THRESHOLDS[dimension]
            and metric.precision_lower_bound is not None
            and metric.precision_lower_bound >= MINIMUM_PRECISION_LOWER_BOUND
        ):
            fact.quality_state = "published"
        else:
            fact.quality_state = "quarantined"
        fact.quality_policy_version = POLICY_VERSION
        return self._finish(fact, commit)

    def reevaluate_dimension(self, dimension: str) -> int:
        fact_key = FACT_KEYS_BY_DIMENSION.get(dimension)
        if fact_key is None:
            return 0
        facts = list(
            self.session.scalars(
                select(BusinessFactModel).where(BusinessFactModel.fact_key == fact_key)
            )
        )
        for fact in facts:
            self.evaluate(fact, commit=False)
        self.session.commit()
        return len(facts)

    def _latest_metric(
        self,
        dimension: str,
        *,
        source: str | None,
    ) -> QualityMetricSnapshotModel | None:
        metrics = list(
            self.session.scalars(
                select(QualityMetricSnapshotModel)
                .where(
                    QualityMetricSnapshotModel.dimension == dimension,
                    or_(
                        QualityMetricSnapshotModel.source == source,
                        QualityMetricSnapshotModel.source.is_(None),
                    ),
                    QualityMetricSnapshotModel.niche_id.is_(None),
                    QualityMetricSnapshotModel.market_key.is_(None),
                )
                .order_by(QualityMetricSnapshotModel.calculated_at.desc())
            )
        )
        if not metrics:
            return None
        metrics.sort(
            key=lambda metric: (
                metric.source == source and source is not None,
                metric.calculated_at,
            ),
            reverse=True,
        )
        return metrics[0]

    def _finish(
        self,
        fact: BusinessFactModel,
        commit: bool,
    ) -> BusinessFactModel:
        if commit:
            self.session.commit()
            self.session.refresh(fact)
        else:
            self.session.flush()
        return fact
