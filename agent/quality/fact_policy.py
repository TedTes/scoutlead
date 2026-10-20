from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import BusinessFactModel


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
        dimension = FACT_DIMENSIONS.get(fact.fact_key)
        if dimension is None:
            fact.quality_state = "published"
            fact.quality_policy_version = POLICY_VERSION
            return self._finish(fact, commit)
        # Opportunity claims stay staged until the explicit signal-validation
        # workflow publishes them. Population metrics are no longer persisted.
        fact.quality_state = "staged"
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
