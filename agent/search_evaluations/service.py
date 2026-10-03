from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.llm import LLMClient
from business_facts.repository import BusinessFactRepository, fact_value
from business_index.schemas import SearchContract
from db.models import BusinessModel, ContactModel, SourceObservationModel
from search_evaluations.repository import SearchEvaluationRepository
from search_evaluations.schemas import (
    BusinessSearchEvaluationResult,
    SearchEvaluationBatchResult,
    SearchEvaluationResult,
)
from shared.errors import NotFoundError
from shared.logger import get_logger


logger = get_logger(__name__)


class SearchEvaluationService:
    def __init__(self, *, session: Session, llm: LLMClient) -> None:
        self.session = session
        self.llm = llm
        self.repository = SearchEvaluationRepository(session)

    def evaluate(
        self,
        *,
        business_id: str,
        contract_hash: str,
        contract: SearchContract,
        evidence_fresh_after: datetime | None = None,
    ):
        business = self.session.get(BusinessModel, business_id)
        if business is None:
            raise NotFoundError("business not found", {"business_id": business_id})
        facts = BusinessFactRepository(self.session).map_for_businesses([business_id]).get(
            business_id, {}
        )
        if evidence_fresh_after is not None:
            facts = {
                key: fact
                for key, fact in facts.items()
                if _aware(fact.observed_at) >= _aware(evidence_fresh_after)
            }
        contacts = list(
            self.session.scalars(
                select(ContactModel).where(ContactModel.business_id == business_id)
            )
        )
        observation_query = select(SourceObservationModel).where(
            SourceObservationModel.business_id == business_id
        )
        if evidence_fresh_after is not None:
            observation_query = observation_query.where(
                SourceObservationModel.observed_at >= evidence_fresh_after
            )
        observations = list(
            self.session.scalars(
                observation_query.order_by(SourceObservationModel.observed_at.desc()).limit(12)
            )
        )
        result = self.llm.generate_object(
            task="search_criteria_evaluation",
            system=(
                "Evaluate only the supplied criteria against supplied public evidence. "
                "Do not infer missing facts. Required criteria must all match. At least one "
                "alternative criterion must match when alternatives exist. Reject when an "
                "exclusion is supported. Return unknown when evidence is insufficient."
            ),
            prompt="Evaluate this business against the saved search contract.",
            response_model=SearchEvaluationResult,
            context={
                "business": {
                    "id": business.id,
                    "name": business.display_name,
                    "website": business.website_url,
                    "geography": business.geography or business.address,
                    "description": business.semantic_text,
                },
                "semantic_contract": {
                    "required": list(contract.semantic_all_of),
                    "alternatives": list(contract.semantic_any_of),
                    "exclusions": list(contract.semantic_exclusions),
                },
                "current_facts": {
                    key: {
                        "value": fact_value(fact),
                        "observed_at": fact.observed_at.isoformat(),
                        "confidence": fact.confidence,
                    }
                    for key, fact in facts.items()
                },
                "contacts": [
                    {"email": item.email, "phone": item.phone} for item in contacts
                ],
                "source_observations": [
                    {
                        "source": item.source,
                        "source_url": item.source_url,
                        "observed_at": item.observed_at.isoformat(),
                        "payload": item.raw_payload,
                    }
                    for item in observations
                ],
            },
        )
        return self.repository.save(
            business_id=business_id,
            contract_hash=contract_hash,
            contract_version=contract.version,
            result=result,
        )

    def evaluate_batch(
        self,
        *,
        business_ids: list[str],
        contract_hash: str,
        contract: SearchContract,
        evidence_fresh_after: datetime | None = None,
    ) -> list:
        unique_ids = list(dict.fromkeys(business_ids))[:25]
        evidence = [
            item
            for business_id in unique_ids
            if (item := self._compact_evidence(business_id, evidence_fresh_after)) is not None
        ]
        if not evidence:
            return []
        context = {
            "semantic_contract": {
                "required": list(contract.semantic_all_of),
                "alternatives": list(contract.semantic_any_of),
                "exclusions": list(contract.semantic_exclusions),
            },
            "businesses": evidence,
        }
        batch = self.llm.generate_object(
            task="search_criteria_evaluation_batch",
            system=(
                "Evaluate each business independently against only the supplied semantic criteria. "
                "Do not infer missing facts. Required criteria must all match; one alternative must "
                "match when alternatives exist; reject when an exclusion is supported. Return "
                "unknown when evidence is insufficient. Return exactly one result per business_id."
            ),
            prompt="Evaluate this candidate batch against the saved search contract.",
            response_model=SearchEvaluationBatchResult,
            context=context,
        )
        estimated_input_tokens = max(1, len(json.dumps(context, default=str)) // 4)
        logger.info(
            "search_evaluation_batch candidate_count=%s estimated_input_tokens=%s usage=%s",
            len(evidence),
            estimated_input_tokens,
            getattr(self.llm, "last_usage", {}),
        )
        by_id = {item.business_id: item for item in batch.results}
        saved = []
        for business_id in unique_ids:
            item = by_id.get(business_id)
            if item is None:
                item = BusinessSearchEvaluationResult(
                    business_id=business_id,
                    status="unknown",
                    confidence=0,
                    rationale="The evaluator did not return a result for this candidate.",
                    missing_evidence=["Candidate evaluation result"],
                )
            saved.append(
                self.repository.save(
                    business_id=business_id,
                    contract_hash=contract_hash,
                    contract_version=contract.version,
                    result=SearchEvaluationResult.model_validate(
                        item.model_dump(exclude={"business_id"})
                    ),
                )
            )
        return saved

    def _compact_evidence(
        self,
        business_id: str,
        evidence_fresh_after: datetime | None,
    ) -> dict | None:
        business = self.session.get(BusinessModel, business_id)
        if business is None:
            return None
        facts = BusinessFactRepository(self.session).map_for_businesses([business_id]).get(
            business_id, {}
        )
        contacts = list(
            self.session.scalars(
                select(ContactModel).where(ContactModel.business_id == business_id)
            )
        )
        query = select(SourceObservationModel).where(
            SourceObservationModel.business_id == business_id
        )
        if evidence_fresh_after is not None:
            query = query.where(SourceObservationModel.observed_at >= evidence_fresh_after)
        observations = list(
            self.session.scalars(query.order_by(SourceObservationModel.observed_at.desc()).limit(5))
        )
        return {
            "id": business.id,
            "name": business.display_name,
            "category": business.category_key,
            "geography": business.geography or business.address,
            "website": business.website_url,
            "description": business.semantic_text,
            "facts": {key: fact_value(fact) for key, fact in facts.items()},
            "contacts": [
                {"email": bool(item.email), "phone": bool(item.phone)} for item in contacts
            ],
            "observations": [
                {
                    "source": item.source,
                    "url": item.source_url,
                    "summary": _payload_summary(item.raw_payload or {}),
                }
                for item in observations
            ],
        }


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _payload_summary(payload: dict) -> dict:
    allowed = {
        "title", "name", "description", "snippet", "category", "categories",
        "businessStatus", "address", "websiteUri", "url", "rating", "userRatingCount",
    }
    return {key: value for key, value in payload.items() if key in allowed}
