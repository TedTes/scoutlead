from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from business_facts.repository import BusinessFactRepository, fact_value
from db.models import (
    BusinessModel,
    BusinessSearchEvaluationModel,
    ContactModel,
    SourceObservationModel,
)
from search_evaluations.schemas import SearchEvaluationResult
from shared.utils import new_id, utcnow


class SearchEvaluationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def current(
        self,
        *,
        business_id: str,
        contract_hash: str,
    ) -> BusinessSearchEvaluationModel | None:
        fingerprint = evidence_fingerprint(self.session, business_id)
        return self.session.scalar(
            select(BusinessSearchEvaluationModel)
            .where(
                BusinessSearchEvaluationModel.business_id == business_id,
                BusinessSearchEvaluationModel.contract_hash == contract_hash,
                BusinessSearchEvaluationModel.evidence_fingerprint == fingerprint,
            )
            .order_by(BusinessSearchEvaluationModel.evaluated_at.desc())
            .limit(1)
        )

    def save(
        self,
        *,
        business_id: str,
        contract_hash: str,
        contract_version: int,
        result: SearchEvaluationResult,
    ) -> BusinessSearchEvaluationModel:
        fingerprint = evidence_fingerprint(self.session, business_id)
        existing = self.current(business_id=business_id, contract_hash=contract_hash)
        model = existing or BusinessSearchEvaluationModel(
            id=new_id("search_evaluation"),
            business_id=business_id,
            contract_hash=contract_hash,
            contract_version=contract_version,
            evidence_fingerprint=fingerprint,
            status=result.status.value,
            confidence=result.confidence,
            rationale=result.rationale,
            criterion_results=[],
            evidence=[],
            missing_evidence=[],
            evaluated_at=utcnow(),
        )
        model.contract_version = contract_version
        model.status = result.status.value
        model.confidence = result.confidence
        model.rationale = result.rationale
        model.criterion_results = [item.model_dump(mode="json") for item in result.criteria]
        model.evidence = result.evidence
        model.missing_evidence = result.missing_evidence
        model.evaluated_at = utcnow()
        if existing is None:
            self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return model


def evidence_fingerprint(session: Session, business_id: str) -> str:
    business = session.get(BusinessModel, business_id)
    facts = BusinessFactRepository(session).map_for_businesses([business_id]).get(
        business_id, {}
    )
    observations = list(
        session.scalars(
            select(SourceObservationModel)
            .where(SourceObservationModel.business_id == business_id)
            .order_by(SourceObservationModel.observed_at.desc())
            .limit(25)
        )
    )
    contacts = list(
        session.scalars(
            select(ContactModel)
            .where(ContactModel.business_id == business_id)
            .order_by(ContactModel.updated_at.desc())
        )
    )
    payload = {
        "business": (
            {
                "name": business.display_name,
                "website": business.website_url,
                "phone": business.phone,
                "address": business.address,
                "geography": business.geography,
                "category": business.category_key,
                "description": business.semantic_text,
                "status": business.status,
            }
            if business is not None
            else None
        ),
        "facts": {
            key: [fact_value(fact), fact.confidence]
            for key, fact in sorted(facts.items())
        },
        "observations": sorted(
            {f"{item.source}:{item.content_hash}" for item in observations}
        ),
        "contacts": sorted(
            (
                [
                    item.name,
                    item.role,
                    item.email,
                    item.phone,
                    item.verification_status,
                ]
                for item in contacts
            ),
            key=lambda item: json.dumps(item, separators=(",", ":")),
        ),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
