from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from business_attributes.repository import BusinessAttributeRepository, attribute_value
from business_attributes.service import reconcile_business_attributes
from business_index.schemas import (
    BusinessIndexSearch,
    FactOperator,
    FactPredicate,
)
from canonical.semantics import market_is_compatible
from db.models import (
    BusinessModel,
    BusinessNicheMembershipModel,
    ContactModel,
    BusinessAttributeModel,
)
from evaluation.digital_opportunity import opportunity_evidence_from_sources
from seeding.batches import active_membership_condition, observation_is_quarantined


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
        rows, decisions = self._search(request, include_unknown=False)
        return rows, decisions

    def search_candidates_with_diagnostics(
        self,
        request: BusinessIndexSearch,
    ) -> tuple[list[dict], list[dict]]:
        """Return matched and unresolved candidates for one user-visible run."""
        return self._search(request, include_unknown=True)

    def _search(
        self,
        request: BusinessIndexSearch,
        *,
        include_unknown: bool,
    ) -> tuple[list[dict], list[dict]]:
        decisions: list[dict] = []
        memberships = list(
            self.session.scalars(
                select(BusinessNicheMembershipModel)
                .where(BusinessNicheMembershipModel.niche_id == request.niche_id)
                .where(active_membership_condition())
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
        businesses = {
            business.id: business
            for business in self.session.scalars(
                select(BusinessModel).where(
                    BusinessModel.id.in_(business_ids),
                    BusinessModel.status == "active",
                )
            )
        }
        # Older indexed businesses may predate the fact table. Reconciliation is
        # database-only and makes the canonical record and observations queryable.
        for business_id in businesses:
            reconcile_business_attributes(self.session, business_id)
        facts_by_business = BusinessAttributeRepository(self.session).map_for_businesses(
            business_ids
        )
        contacts: dict[str, list[ContactModel]] = defaultdict(list)
        for contact in self.session.scalars(
            select(ContactModel).where(ContactModel.business_id.in_(business_ids))
        ):
            contacts[contact.business_id].append(contact)
        observations: dict[str, list[BusinessAttributeModel]] = defaultdict(list)
        for observation in self.session.scalars(
            select(BusinessAttributeModel)
            .where(
                BusinessAttributeModel.business_id.in_(business_ids),
                BusinessAttributeModel.observed_at >= request.evidence_fresh_after,
            )
            .order_by(BusinessAttributeModel.observed_at.desc())
        ):
            if observation_is_quarantined(self.session, observation):
                continue
            observations[observation.business_id].append(observation)
        latest_listings: dict[str, BusinessAttributeModel] = {}
        for observation in self.session.scalars(
            select(BusinessAttributeModel)
            .where(
                BusinessAttributeModel.business_id.in_(business_ids),
                BusinessAttributeModel.source.notin_(
                    ["website_presence_check", "company_website_seed"]
                ),
            )
            .order_by(BusinessAttributeModel.observed_at.desc())
        ):
            if observation_is_quarantined(self.session, observation):
                continue
            latest_listings.setdefault(observation.business_id, observation)

        ranked: list[tuple[tuple, dict]] = []
        unresolved: list[tuple[tuple, dict]] = []
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
            business_attributes = facts_by_business.get(business.id, {})
            contract_status, match_reason, opportunity_score, matched_at = _evaluate_contract(
                business_attributes,
                request=request,
            )
            if contract_status == "not_matched":
                decisions.append(
                    _decision(
                        business.id,
                        business.display_name,
                        "rejected",
                        match_reason,
                    )
                )
                continue
            business_contacts = contacts.get(business.id, [])
            if not _contacts_match(
                request.contract.contact_requirements,
                business=business,
                contacts=business_contacts,
            ):
                decisions.append(
                    _decision(
                        business.id,
                        business.display_name,
                        "rejected",
                        "Current contacts do not satisfy the requested contact requirements.",
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
            contact = _best_contact(business_contacts)
            candidate_status = contract_status
            raw = {
                **(listing_observation.raw_payload or {} if listing_observation else {}),
                "match_origin": "business_index",
                "canonical_business_id": business.id,
                "source_evidence_id": listing_observation.id if listing_observation else None,
                "business_index_opportunity_evidence": (
                    opportunity_observation.raw_payload
                    if opportunity_observation is not None
                    else None
                ),
                "business_index_evidence_observed_at": (
                    matched_at.isoformat() if matched_at is not None else None
                ),
                "business_attributes": _serialize_facts(business_attributes),
                "search_contract": request.contract.as_dict(),
                "search_contract_hash": request.contract_hash,
                "search_match": {
                    "status": candidate_status,
                    "reason": (
                        match_reason
                        if candidate_status == "unknown"
                        else "Matched current evidence."
                    ),
                },
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
                100,
                _contact_rank(contact, business),
                membership.confidence,
                matched_at.timestamp() if matched_at is not None else 0,
            )
            if candidate_status == "unknown":
                decisions.append(
                    _decision(
                        business.id,
                        business.display_name,
                        "unknown",
                        "Current evidence is incomplete for one or more requested criteria.",
                    )
                )
                unresolved.append((rank, row))
            else:
                ranked.append((rank, row))
        ranked.sort(key=lambda item: item[0], reverse=True)
        unresolved.sort(key=lambda item: item[0], reverse=True)
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
        rows = [row for _, row in selected]
        if include_unknown and len(rows) < request.result_count:
            rows.extend(row for _, row in unresolved[: request.result_count - len(rows)])
        return rows, decisions


def _evaluate_contract(
    facts: dict,
    *,
    request: BusinessIndexSearch,
) -> tuple[str, str, int, datetime | None]:
    contract = request.contract
    fresh_facts = {
        key: fact
        for key, fact in facts.items()
        if _aware(fact.observed_at) >= _aware(request.evidence_fresh_after)
        and (
            fact.expires_at is None
            or _aware(fact.expires_at) >= _aware(request.evidence_fresh_after)
        )
    }
    for predicate in contract.all_of:
        if predicate.key not in fresh_facts:
            return "unknown", _predicate_failure(predicate, fresh_facts), 0, None
        predicate_status = _predicate_status(fresh_facts.get(predicate.key), predicate)
        if predicate_status == "unknown":
            return "unknown", _predicate_unknown_reason(predicate), 0, None
        if predicate_status == "not_matched":
            return "not_matched", _predicate_failure(predicate, fresh_facts), 0, None
    if contract.any_of:
        known = [predicate for predicate in contract.any_of if predicate.key in fresh_facts]
        statuses = [
            _predicate_status(fresh_facts[predicate.key], predicate) for predicate in known
        ]
        if "matched" in statuses:
            pass
        elif len(known) < len(contract.any_of) or "unknown" in statuses:
            missing = sorted(
                {predicate.key for predicate in contract.any_of if predicate.key not in fresh_facts}
            )
            reason = (
                f"Current facts are unavailable for: {', '.join(missing)}."
                if missing
                else "Current facts are inconclusive for the requested criteria."
            )
            return "unknown", reason, 0, None
        else:
            return (
                "not_matched",
                "Current business facts do not match the requested criteria.",
                0,
                None,
            )
    ranking_matches = [
        predicate
        for predicate in contract.ranking
        if predicate.key in fresh_facts
        and _predicate_matches(fresh_facts[predicate.key], predicate)
    ]
    score = (
        min(100, 60 + (len(ranking_matches) - 1) * 15)
        if ranking_matches
        else (0 if contract.ranking else _opportunity_score(fresh_facts))
    )
    matched_facts = [
        fresh_facts[predicate.key]
        for predicate in (*contract.all_of, *contract.any_of, *ranking_matches)
        if predicate.key in fresh_facts
        and _predicate_matches(fresh_facts[predicate.key], predicate)
    ]
    matched_at = max((fact.observed_at for fact in matched_facts), default=None)
    warning = (
        f"Matched supported criteria; unsupported criteria: {', '.join(contract.unsupported)}."
        if contract.unsupported
        else "Matched current business facts."
    )
    return "matched", warning, score, matched_at


def _predicate_matches(fact, predicate: FactPredicate) -> bool:
    value = attribute_value(fact)
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


def _predicate_status(fact, predicate: FactPredicate) -> str:
    value = attribute_value(fact)
    if value is None or value == "unknown":
        return "unknown"
    if (
        predicate.key == "website_status"
        and value == "not_listed"
        and predicate.value != "not_listed"
    ):
        return "unknown"
    return "matched" if _predicate_matches(fact, predicate) else "not_matched"


def _predicate_failure(predicate: FactPredicate, facts: dict) -> str:
    if predicate.key not in facts:
        return f"Current fact is unavailable: {predicate.key}."
    return f"Current fact does not match: {predicate.key}."


def _predicate_unknown_reason(predicate: FactPredicate) -> str:
    if predicate.key == "website_status":
        return "Website presence has not been verified."
    return f"Current fact is inconclusive: {predicate.key}."


def _opportunity_score(facts: dict) -> int:
    score = 0
    website_status = attribute_value(facts.get("website_status"))
    if website_status == "missing":
        score += 65
    elif website_status in {"unavailable", "parked"}:
        score += 55
    website_quality = attribute_value(facts.get("website_quality_score"))
    if isinstance(website_quality, (int, float)) and website_quality < 75:
        score += round(75 - float(website_quality))
    rating = attribute_value(facts.get("google_rating"))
    if isinstance(rating, (int, float)) and rating < 4.3:
        score += 20
    reviews = attribute_value(facts.get("google_review_count"))
    if isinstance(reviews, (int, float)) and reviews < 20:
        score += 15
    return min(score, 100)


def _serialize_facts(facts: dict) -> dict:
    return {
        key: {
            "value": attribute_value(fact),
            "observed_at": fact.observed_at.isoformat(),
            "confidence": fact.confidence,
            "source": fact.source_provider,
            "source_url": fact.source_url,
            "evidence_hash": fact.evidence_hash,
        }
        for key, fact in facts.items()
    }


def _contacts_match(
    requirements: tuple[str, ...],
    *,
    business: BusinessModel,
    contacts: list[ContactModel],
) -> bool:
    if not requirements:
        return True
    has_email = any(bool(contact.email) for contact in contacts)
    has_phone = bool(business.phone) or any(bool(contact.phone) for contact in contacts)
    values = {
        "email": has_email,
        "phone": has_phone,
        "any_contact": has_email or has_phone,
    }
    return all(values.get(requirement, False) for requirement in requirements)


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
