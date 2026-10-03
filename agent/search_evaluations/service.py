from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.llm import LLMClient
from business_facts.repository import BusinessFactRepository, fact_value
from business_index.schemas import SearchContract
from db.models import BusinessModel, ContactModel, SourceObservationModel
from search_evaluations.repository import SearchEvaluationRepository
from search_evaluations.schemas import SearchEvaluationResult
from shared.errors import NotFoundError


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


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
