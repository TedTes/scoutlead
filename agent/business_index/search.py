from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from business_facts.repository import BusinessFactRepository, fact_value
from business_index.schemas import (
    BusinessIndexSearch,
    FactOperator,
    FactPredicate,
    OpportunityType,
    SearchContract,
)
from canonical.semantics import market_is_compatible
from db.models import (
    BusinessModel,
    BusinessNicheMembershipModel,
    ContactModel,
    SourceObservationModel,
)
from evaluation.digital_opportunity import opportunity_evidence_from_sources


class BusinessIndexSearchService:
    """Query only durable indexed data; this service never calls external providers."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def search(self, request: BusinessIndexSearch) -> list[dict]:
        rows, _ = self.search_with_diagnostics(request)
        return rows

    def search_with_diagnostics(
        self,
        request: BusinessIndexSearch,
    ) -> tuple[list[dict], list[dict]]:
        decisions: list[dict] = []
        memberships = list(
            self.session.scalars(
                select(BusinessNicheMembershipModel)
                .where(BusinessNicheMembershipModel.niche_id == request.niche_id)
                .order_by(
                    BusinessNicheMembershipModel.confidence.desc(),
                    BusinessNicheMembershipModel.last_seen_at.desc(),
                )
            )
        )
        memberships = [
            membership
            for membership in memberships
            if market_is_compatible(request.market_key, membership.market_key)
        ]
        if not memberships:
            return [], decisions
        business_ids = list(dict.fromkeys(item.business_id for item in memberships))
        facts_by_business = BusinessFactRepository(self.session).map_for_businesses(
            business_ids
        )
        businesses = {
            business.id: business
            for business in self.session.scalars(
                select(BusinessModel).where(
                    BusinessModel.id.in_(business_ids),
                    BusinessModel.status == "active",
                )
            )
        }
        contacts: dict[str, list[ContactModel]] = defaultdict(list)
        for contact in self.session.scalars(
            select(ContactModel).where(ContactModel.business_id.in_(business_ids))
        ):
            contacts[contact.business_id].append(contact)
        observations: dict[str, list[SourceObservationModel]] = defaultdict(list)
        for observation in self.session.scalars(
            select(SourceObservationModel)
            .where(
                SourceObservationModel.business_id.in_(business_ids),
                SourceObservationModel.observed_at >= request.evidence_fresh_after,
            )
            .order_by(SourceObservationModel.observed_at.desc())
        ):
            observations[observation.business_id].append(observation)
        latest_listings: dict[str, SourceObservationModel] = {}
        for observation in self.session.scalars(
            select(SourceObservationModel)
            .where(
                SourceObservationModel.business_id.in_(business_ids),
                SourceObservationModel.source.notin_(
                    ["website_presence_check", "company_website_seed"]
                ),
            )
            .order_by(SourceObservationModel.observed_at.desc())
        ):
            latest_listings.setdefault(observation.business_id, observation)

        ranked: list[tuple[tuple, dict]] = []
        for membership in memberships:
            business = businesses.get(membership.business_id)
            if business is None:
                decisions.append(
                    _decision(
                        membership.business_id,
                        None,
                        "rejected",
                        "Business is missing or is not active.",
                    )
                )
                continue
            business_observations = observations.get(business.id, [])
            business_facts = facts_by_business.get(business.id, {})
            matched, match_reason, opportunity_score, matched_at = _evaluate_contract(
                business_facts,
                request=request,
            )
            if not matched:
                decisions.append(
                    _decision(
                        business.id,
                        business.display_name,
                        "rejected",
                        match_reason,
                    )
                )
                continue
            opportunity_observation = next(
                (
                    observation
                    for observation in business_observations
                    if opportunity_evidence_from_sources([observation.raw_payload]) is not None
                ),
                None,
            )
            listing_observation = latest_listings.get(
                business.id,
                opportunity_observation,
            )
            contact = _best_contact(contacts.get(business.id, []))
            raw = {
                **(listing_observation.raw_payload or {} if listing_observation else {}),
                "match_origin": "business_index",
                "canonical_business_id": business.id,
                "source_observation_id": listing_observation.id if listing_observation else None,
                "business_index_opportunity_evidence": (
                    opportunity_observation.raw_payload
                    if opportunity_observation is not None
                    else None
                ),
                "business_index_evidence_observed_at": (
                    matched_at.isoformat() if matched_at is not None else None
                ),
                "business_facts": _serialize_facts(business_facts),
                "search_contract": request.contract.as_dict(),
                "niche_membership": {
                    "id": membership.id,
                    "niche_id": membership.niche_id,
                    "market_key": membership.market_key,
                    "confidence": membership.confidence,
                },
            }
            row = {
                "title": business.display_name,
                "url": business.website_url,
                "snippet": business.semantic_text,
                "geography": business.geography or business.address,
                "contact_email": contact.email if contact else None,
                "source": listing_observation.source if listing_observation else "business_index",
                "raw": raw,
            }
            rank = (
                opportunity_score,
                _contact_rank(contact, business),
                membership.confidence,
                matched_at.timestamp() if matched_at is not None else 0,
            )
            ranked.append((rank, row))
        ranked.sort(key=lambda item: item[0], reverse=True)
        selected = ranked[: request.result_count]
        selected_ids = {row["raw"]["canonical_business_id"] for _, row in selected}
        for rank, row in ranked:
            business_id = row["raw"]["canonical_business_id"]
            is_selected = business_id in selected_ids
            decisions.append(
                {
                    **_decision(
                        business_id,
                        row["title"],
                        "accepted" if is_selected else "rejected",
                        "Matched the run contract and was selected."
                        if is_selected
                        else "Matched the contract but fell outside the requested result limit.",
                    ),
                    "rank": list(rank),
                }
            )
        return [row for _, row in selected], decisions


def _evaluate_contract(
    facts: dict,
    *,
    request: BusinessIndexSearch,
) -> tuple[bool, str, int, datetime | None]:
    contract = request.contract
    if not contract.all_of and not contract.any_of:
        contract = _fallback_contract(request.opportunity_type)
    fresh_facts = {
        key: fact
        for key, fact in facts.items()
        if _aware(fact.observed_at) >= _aware(request.evidence_fresh_after)
        and (fact.expires_at is None or _aware(fact.expires_at) >= _aware(request.evidence_fresh_after))
    }
    for predicate in contract.all_of:
        if not _predicate_matches(fresh_facts.get(predicate.key), predicate):
            return False, _predicate_failure(predicate, fresh_facts), 0, None
    if contract.any_of and not any(
        _predicate_matches(fresh_facts.get(predicate.key), predicate)
        for predicate in contract.any_of
    ):
        missing = sorted(
            {predicate.key for predicate in contract.any_of if predicate.key not in fresh_facts}
        )
        if missing:
            return (
                False,
                f"Current facts are unavailable for: {', '.join(missing)}.",
                0,
                None,
            )
        return False, "Current business facts do not match the requested criteria.", 0, None
    if not contract.any_of and request.opportunity_type == OpportunityType.ANY:
        score = _opportunity_score(fresh_facts)
        if score < 25:
            return False, "No current supported opportunity fact was found.", 0, None
    score = _opportunity_score(fresh_facts)
    matched_facts = [
        fresh_facts[predicate.key]
        for predicate in (*contract.all_of, *contract.any_of)
        if predicate.key in fresh_facts
        and _predicate_matches(fresh_facts[predicate.key], predicate)
    ]
    matched_at = max((fact.observed_at for fact in matched_facts), default=None)
    warning = (
        f"Matched supported criteria; unsupported criteria: {', '.join(contract.unsupported)}."
        if contract.unsupported
        else "Matched current business facts."
    )
    return True, warning, score, matched_at


def _fallback_contract(opportunity_type: OpportunityType) -> SearchContract:
    from business_index.contracts import compile_search_contract

    return compile_search_contract(None, opportunity_type=opportunity_type)


def _predicate_matches(fact, predicate: FactPredicate) -> bool:
    value = fact_value(fact)
    if value is None:
        return False
    expected = predicate.value
    if predicate.operator == FactOperator.EQUALS:
        return value == expected
    if predicate.operator == FactOperator.IN:
        return value in expected
    try:
        numeric = float(value)
        target = float(expected)
    except (TypeError, ValueError):
        return False
    if predicate.operator == FactOperator.LESS_THAN:
        return numeric < target
    if predicate.operator == FactOperator.LESS_THAN_OR_EQUAL:
        return numeric <= target
    if predicate.operator == FactOperator.GREATER_THAN:
        return numeric > target
    return numeric >= target


def _predicate_failure(predicate: FactPredicate, facts: dict) -> str:
    if predicate.key not in facts:
        return f"Current fact is unavailable: {predicate.key}."
    return f"Current fact does not match: {predicate.key}."


def _opportunity_score(facts: dict) -> int:
    score = 0
    website_status = fact_value(facts.get("website_status"))
    if website_status == "missing":
        score += 65
    elif website_status in {"unavailable", "parked"}:
        score += 55
    if fact_value(facts.get("quote_or_booking_form_present")) is False:
        score += 30
    if fact_value(facts.get("contact_form_present")) is False:
        score += 15
    rating = fact_value(facts.get("google_rating"))
    if isinstance(rating, (int, float)) and rating < 4.3:
        score += 20
    reviews = fact_value(facts.get("google_review_count"))
    if isinstance(reviews, (int, float)) and reviews < 20:
        score += 15
    return min(score, 100)


def _serialize_facts(facts: dict) -> dict:
    return {
        key: {
            "value": fact_value(fact),
            "observed_at": fact.observed_at.isoformat(),
            "confidence": fact.confidence,
            "source_observation_id": fact.source_observation_id,
            "resolver_version": fact.resolver_version,
        }
        for key, fact in facts.items()
    }


def _decision(
    business_id: str,
    company_name: str | None,
    status: str,
    reason: str,
) -> dict:
    return {
        "business_id": business_id,
        "company_name": company_name,
        "status": status,
        "reason": reason,
    }


def _best_contact(contacts: list[ContactModel]) -> ContactModel | None:
    if not contacts:
        return None
    status_rank = {"valid": 4, "risky": 3, "unknown": 2, "unverified": 1, "invalid": 0}
    return max(
        contacts,
        key=lambda contact: (
            bool(contact.email),
            status_rank.get(contact.verification_status, 0),
            bool(contact.phone),
            contact.last_seen_at,
        ),
    )


def _contact_rank(contact: ContactModel | None, business: BusinessModel) -> int:
    if contact and contact.email and contact.verification_status == "valid":
        return 4
    if contact and contact.email:
        return 3
    if (contact and contact.phone) or business.phone:
        return 2
    return 0


def _aware(value):
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
