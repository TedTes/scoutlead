from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import BusinessFactModel, SignalDefinitionModel
from quality.fact_usability import (
    FACT_USABILITY_POLICY_VERSION,
    assess_fact_usability,
)


FACT_DIMENSIONS = {
    "website_status": "website_unavailable",
    "google_review_count": "reviews_under_15",
    "quote_or_booking_form_present": "no_quote_flow",
    "contact_form_present": "no_contact_form",
    "uses_https": "missing_https",
    "mobile_viewport_present": "missing_mobile_viewport",
    "primary_cta_present": "no_primary_cta",
    "click_to_call_present": "no_click_to_call",
    "online_payment_or_financing_present": "no_online_payment_or_financing",
    "service_area_pages_present": "no_service_area_pages",
    "service_area_content_present": "no_service_area_pages",
}
FACT_KEYS_BY_DIMENSION = {value: key for key, value in FACT_DIMENSIONS.items()}
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
        definition = (
            self.session.get(SignalDefinitionModel, fact.signal_definition_id)
            if fact.signal_definition_id
            else None
        )
        # ``business_operational`` predates the attribute-definition catalog and
        # is also used by lightweight/test databases. Preserve its canonical
        # eligibility role when the catalog row has not been installed yet.
        if definition is None and fact.fact_key == "business_operational":
            fact.quality_state = (
                "published"
                if fact.resolution_state == "confirmed"
                and fact.source_observation_id is not None
                and fact.attribute_score is not None
                else "staged"
            )
            fact.quality_policy_version = FACT_USABILITY_POLICY_VERSION
            return self._finish(fact, commit)
        observation = fact.source_observation
        validation = None
        if definition is not None and bool((definition.config or {}).get("requires_validation", True)):
            from db.models import ValidationResultModel

            validation = self.session.scalar(
                select(ValidationResultModel)
                .where(
                    ValidationResultModel.business_id == fact.business_id,
                    ValidationResultModel.validation_type == f"signal:{fact.fact_key}",
                )
                .order_by(
                    ValidationResultModel.observed_at.desc(),
                    ValidationResultModel.created_at.desc(),
                    ValidationResultModel.id.desc(),
                )
                .limit(1)
            )
        decision = assess_fact_usability(
            fact,
            definition=definition,
            observation=observation,
            validation=validation,
        )
        if decision.useful:
            fact.quality_state = "published"
            fact.quality_policy_version = FACT_USABILITY_POLICY_VERSION
            return self._finish(fact, commit)
        fact.quality_state = "staged"
        fact.quality_policy_version = FACT_USABILITY_POLICY_VERSION
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
