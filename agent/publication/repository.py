from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import BusinessPublicationModel, ValidationResultModel
from shared.utils import new_id


@dataclass(frozen=True)
class ValidationResult:
    business_id: str
    source_item_id: str | None
    source_observation_id: str | None
    validation_type: str
    status: str
    confidence: int
    reason: str
    evidence: list[dict]
    validator: str
    validator_version: int
    observed_at: datetime
    expires_at: datetime
    niche_id: str | None = None
    market_key: str | None = None

    @property
    def idempotency_key(self) -> str:
        source = (
            self.source_item_id
            or self.source_observation_id
            or f"{self.business_id}:{self.observed_at.date().isoformat()}"
        )
        return (
            f"{source}:{self.niche_id or '*'}:{self.market_key or '*'}:"
            f"{self.validation_type}:{self.validator}:{self.validator_version}"
        )


class ValidationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record(self, result: ValidationResult) -> ValidationResultModel:
        existing = self.session.scalar(
            select(ValidationResultModel)
            .where(ValidationResultModel.idempotency_key == result.idempotency_key)
            .limit(1)
        )
        if existing is not None:
            return existing
        model = ValidationResultModel(
            id=new_id("validation"),
            idempotency_key=result.idempotency_key,
            business_id=result.business_id,
            source_item_id=result.source_item_id,
            source_observation_id=result.source_observation_id,
            niche_id=result.niche_id,
            market_key=result.market_key,
            validation_type=result.validation_type,
            status=result.status,
            confidence=max(0, min(100, result.confidence)),
            reason=result.reason,
            evidence=result.evidence,
            validator=result.validator,
            validator_version=result.validator_version,
            observed_at=result.observed_at,
            expires_at=result.expires_at,
        )
        self.session.add(model)
        self.session.flush()
        return model

    def latest_current(
        self,
        business_id: str,
        *,
        niche_id: str,
        market_key: str,
        now: datetime,
    ) -> dict[str, ValidationResultModel]:
        rows = list(
            self.session.scalars(
            select(ValidationResultModel)
            .where(
                ValidationResultModel.business_id == business_id,
                ValidationResultModel.expires_at >= now,
            )
            .order_by(ValidationResultModel.observed_at.desc())
            )
        )
        rows = [
            row
            for row in rows
            if row.niche_id in {None, niche_id}
            and row.market_key in {None, market_key}
        ]
        rows.sort(
            key=lambda row: (
                row.niche_id == niche_id,
                row.market_key == market_key,
                row.observed_at,
            ),
            reverse=True,
        )
        latest: dict[str, ValidationResultModel] = {}
        for row in rows:
            latest.setdefault(row.validation_type, row)
        return latest


class PublicationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(
        self,
        *,
        business_id: str,
        niche_id: str,
        market_key: str,
        status: str,
        policy_version: int,
        reasons: list[dict],
        evaluated_at: datetime,
        expires_at: datetime | None,
        commit: bool = True,
    ) -> BusinessPublicationModel:
        model = self.session.scalar(
            select(BusinessPublicationModel)
            .where(
                BusinessPublicationModel.business_id == business_id,
                BusinessPublicationModel.niche_id == niche_id,
                BusinessPublicationModel.market_key == market_key,
            )
            .limit(1)
        )
        if model is None:
            model = BusinessPublicationModel(
                id=new_id("publication"),
                business_id=business_id,
                niche_id=niche_id,
                market_key=market_key,
                status=status,
                policy_version=policy_version,
                reasons=reasons,
                evaluated_at=evaluated_at,
                expires_at=expires_at,
            )
            self.session.add(model)
        else:
            model.status = status
            model.policy_version = policy_version
            model.reasons = reasons
            model.evaluated_at = evaluated_at
            model.expires_at = expires_at
        if commit:
            self.session.commit()
            self.session.refresh(model)
        else:
            self.session.flush()
        return model
