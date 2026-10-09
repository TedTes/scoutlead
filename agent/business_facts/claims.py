from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import FactClaimModel
from shared.utils import new_id


@dataclass(frozen=True)
class FactClaim:
    business_id: str
    fact_key: str
    value: Any
    source_observation_id: str
    confidence: int
    extractor: str
    extractor_version: int
    observed_at: datetime
    expires_at: datetime

    @property
    def idempotency_key(self) -> str:
        return (
            f"{self.source_observation_id}:{self.fact_key}:"
            f"{self.extractor}:{self.extractor_version}"
        )


class FactClaimRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record(self, claim: FactClaim, *, commit: bool = False) -> FactClaimModel:
        existing = self.session.scalar(
            select(FactClaimModel)
            .where(FactClaimModel.idempotency_key == claim.idempotency_key)
            .limit(1)
        )
        if existing is not None:
            return existing
        model = FactClaimModel(
            id=new_id("fact_claim"),
            idempotency_key=claim.idempotency_key,
            business_id=claim.business_id,
            fact_key=claim.fact_key,
            value=claim.value,
            source_observation_id=claim.source_observation_id,
            confidence=max(0, min(100, claim.confidence)),
            extractor=claim.extractor,
            extractor_version=claim.extractor_version,
            observed_at=claim.observed_at,
            expires_at=claim.expires_at,
        )
        self.session.add(model)
        if commit:
            self.session.commit()
            self.session.refresh(model)
        else:
            self.session.flush()
        return model

    def current_for_business(self, business_id: str, *, now: datetime) -> list[FactClaimModel]:
        return list(
            self.session.scalars(
                select(FactClaimModel)
                .where(
                    FactClaimModel.business_id == business_id,
                    FactClaimModel.expires_at >= now,
                )
                .order_by(FactClaimModel.observed_at.desc(), FactClaimModel.confidence.desc())
            )
        )
