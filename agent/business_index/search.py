from __future__ import annotations

from collections import defaultdict
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from business_index.schemas import BusinessIndexSearch, OpportunityType
from canonical.semantics import market_is_compatible
from db.models import (
    BusinessModel,
    BusinessNicheMembershipModel,
    ContactModel,
    SourceObservationModel,
)
from evaluation.digital_opportunity import (
    opportunity_evidence_from_sources,
    opportunity_signal_keys_from_sources,
)


class BusinessIndexSearchService:
    """Query only durable indexed data; this service never calls external providers."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def search(self, request: BusinessIndexSearch) -> list[dict]:
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
            return []
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
                continue
            business_observations = observations.get(business.id, [])
            opportunity_observation = next(
                (
                    observation
                    for observation in business_observations
                    if opportunity_evidence_from_sources([observation.raw_payload]) is not None
                ),
                None,
            )
            if opportunity_observation is None:
                continue
            if _aware(opportunity_observation.observed_at) < _aware(
                request.evidence_fresh_after
            ):
                continue
            opportunity_sources = [opportunity_observation.raw_payload]
            if "website_unreachable" in opportunity_signal_keys_from_sources(
                opportunity_sources
            ):
                continue
            if not _matches_opportunity_type(opportunity_sources, request.opportunity_type):
                continue
            listing_observation = latest_listings.get(
                business.id,
                opportunity_observation,
            )
            contact = _best_contact(contacts.get(business.id, []))
            evidence = opportunity_evidence_from_sources(opportunity_sources) or {}
            raw = {
                **(listing_observation.raw_payload or {}),
                "match_origin": "business_index",
                "canonical_business_id": business.id,
                "source_observation_id": listing_observation.id,
                "business_index_opportunity_evidence": opportunity_observation.raw_payload,
                "business_index_evidence_observed_at": (
                    opportunity_observation.observed_at.isoformat()
                ),
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
                "source": listing_observation.source,
                "raw": raw,
            }
            rank = (
                int(evidence.get("score") or 0),
                _contact_rank(contact, business),
                membership.confidence,
                opportunity_observation.observed_at.timestamp(),
            )
            ranked.append((rank, row))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [row for _, row in ranked[: request.result_count]]


def _matches_opportunity_type(sources: list[dict], opportunity_type: OpportunityType) -> bool:
    if opportunity_type == OpportunityType.ANY:
        return True
    keys = opportunity_signal_keys_from_sources(sources)
    if opportunity_type == OpportunityType.MISSING_WEBSITE:
        return bool(keys & {"no_website_listed", "no_website_found"})
    return bool(
        keys
        & {
            "no_website_listed",
            "no_website_found",
            "website_unavailable",
            "website_parked",
        }
    )


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
