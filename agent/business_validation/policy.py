from __future__ import annotations

from sqlalchemy.orm import Session

from business_attributes.eligibility import fact_is_eligible
from business_attributes.repository import BusinessAttributeRepository, attribute_value
from db.models import BusinessModel


def business_is_publishable(
    session: Session,
    *,
    business_id: str,
    niche_id: str,
    market_key: str,
    allow_unvalidated: bool = False,
) -> bool:
    business = session.get(BusinessModel, business_id)
    if business is None or business.status != "active":
        return False
    operational = BusinessAttributeRepository(session).map_for_businesses([business_id]).get(
        business_id, {}
    ).get("business_operational")
    if operational is None:
        return True
    if not fact_is_eligible(
        operational,
        minimum_confidence=85,
        require_provenance=True,
    ):
        return True
    return attribute_value(operational) is not False
