from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import sqrt
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import QualityLabelModel, QualityMetricSnapshotModel
from shared.utils import new_id, utcnow


@dataclass(frozen=True)
class QualityScope:
    dimension: str
    source: str | None = None
    niche_id: str | None = None
    market_key: str | None = None
    validator_version: int | None = None


class QualityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_label(
        self,
        *,
        business_id: str,
        scope: QualityScope,
        expected: Any,
        predicted: Any,
        reviewer: str,
        reviewed_at: datetime,
        evidence: list[str] | None = None,
        notes: str | None = None,
        idempotency_key: str | None = None,
        commit: bool = True,
    ) -> QualityLabelModel:
        if idempotency_key:
            existing = self.session.scalar(
                select(QualityLabelModel)
                .where(QualityLabelModel.idempotency_key == idempotency_key)
                .limit(1)
            )
            if existing is not None:
                return existing
        model = QualityLabelModel(
            id=new_id("quality_label"),
            idempotency_key=idempotency_key,
            business_id=business_id,
            dimension=scope.dimension,
            expected=expected,
            predicted=predicted,
            source=scope.source,
            niche_id=scope.niche_id,
            market_key=scope.market_key,
            validator_version=scope.validator_version,
            reviewer=reviewer,
            reviewed_at=reviewed_at,
            evidence=evidence or [],
            notes=notes,
        )
        self.session.add(model)
        if commit:
            self.session.commit()
            self.session.refresh(model)
        else:
            self.session.flush()
        return model

    def calculate(self, scope: QualityScope) -> QualityMetricSnapshotModel:
        statement = select(QualityLabelModel).where(
            QualityLabelModel.dimension == scope.dimension
        )
        for field, value in (
            (QualityLabelModel.source, scope.source),
            (QualityLabelModel.niche_id, scope.niche_id),
            (QualityLabelModel.market_key, scope.market_key),
            (QualityLabelModel.validator_version, scope.validator_version),
        ):
            statement = statement.where(field.is_(None) if value is None else field == value)
        labels = list(self.session.scalars(statement))
        tp = sum(label.expected is True and label.predicted is True for label in labels)
        fp = sum(label.expected is False and label.predicted is True for label in labels)
        fn = sum(label.expected is True and label.predicted is False for label in labels)
        tn = sum(label.expected is False and label.predicted is False for label in labels)
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        model = QualityMetricSnapshotModel(
            id=new_id("quality_metric"),
            dimension=scope.dimension,
            source=scope.source,
            niche_id=scope.niche_id,
            market_key=scope.market_key,
            validator_version=scope.validator_version,
            sample_size=len(labels),
            true_positive=tp,
            false_positive=fp,
            false_negative=fn,
            true_negative=tn,
            precision=precision,
            recall=recall,
            precision_lower_bound=_wilson_lower_bound(tp, tp + fp),
            calculated_at=utcnow(),
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return model


def _wilson_lower_bound(successes: int, total: int, *, z: float = 1.96) -> float | None:
    if total <= 0:
        return None
    proportion = successes / total
    denominator = 1 + z * z / total
    center = proportion + z * z / (2 * total)
    margin = z * sqrt((proportion * (1 - proportion) + z * z / (4 * total)) / total)
    return max(0.0, (center - margin) / denominator)
