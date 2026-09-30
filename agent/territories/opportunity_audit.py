from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from canonical.website_enrichment import SOURCE_NAME, EnrichmentSummary, enrich_business_pool
from db.models import ContactModel, LeadModel, SourceObservationModel
from tools.verify import EmailVerificationTool


class BusinessOpportunityAuditor:
    """Audit the exact businesses selected for a search or recurring delivery."""

    def __init__(
        self,
        *,
        session: Session,
        verifier: EmailVerificationTool | None,
        timeout_seconds: float,
        workers: int = 4,
    ) -> None:
        self.session = session
        self.verifier = verifier
        self.timeout_seconds = timeout_seconds
        self.workers = max(1, workers)

    def audit_campaign(
        self,
        campaign_id: str,
        *,
        category: str | None,
        market: str | None,
    ) -> EnrichmentSummary:
        leads = list(
            self.session.scalars(
                select(LeadModel).where(LeadModel.campaign_id == campaign_id)
            )
        )
        business_ids = list(
            dict.fromkeys(lead.business_id for lead in leads if lead.business_id)
        )
        summary = enrich_business_pool(
            self.session,
            category=category,
            market=market,
            limit=len(business_ids),
            include_with_email=True,
            refresh=False,
            verify=self.verifier is not None,
            timeout_seconds=self.timeout_seconds,
            max_pages_per_business=5,
            page_delay_seconds=0,
            commit_every=max(1, len(business_ids)),
            verifier=self.verifier,
            mark_attempted=True,
            workers=self.workers,
            business_ids=business_ids,
        )
        self._synchronize_leads(leads, business_ids)
        return summary

    def _synchronize_leads(
        self,
        leads: list[LeadModel],
        business_ids: list[str],
    ) -> None:
        if not business_ids:
            return
        observations = list(
            self.session.scalars(
                select(SourceObservationModel)
                .where(
                    SourceObservationModel.business_id.in_(business_ids),
                    SourceObservationModel.source == SOURCE_NAME,
                )
                .order_by(SourceObservationModel.observed_at.desc())
            )
        )
        latest_observation = {}
        for observation in observations:
            latest_observation.setdefault(observation.business_id, observation)

        contacts_by_business: dict[str, list[ContactModel]] = defaultdict(list)
        for contact in self.session.scalars(
            select(ContactModel).where(ContactModel.business_id.in_(business_ids))
        ):
            contacts_by_business[contact.business_id].append(contact)

        for lead in leads:
            if not lead.business_id:
                continue
            observation = latest_observation.get(lead.business_id)
            if observation is not None and not _has_observation(lead, observation.id):
                lead.raw_sources = [
                    *list(lead.raw_sources or []),
                    {
                        "source": observation.source,
                        "source_url": observation.source_url,
                        "source_observation_id": observation.id,
                        "raw": observation.raw_payload,
                    },
                ]
                flag_modified(lead, "raw_sources")

            contact = _best_contact(contacts_by_business.get(lead.business_id, []))
            if contact is None:
                continue
            lead.contact_id = contact.id
            lead.contact_email = contact.email
            lead.verification_status = contact.verification_status
            lead.verification_provider = contact.verification_provider
            lead.verification_checked_at = contact.verification_checked_at
            lead.verification_reason = contact.verification_reason
            lead.verification_score = contact.verification_score
            lead.verification_details = contact.verification_details
        self.session.commit()


def _best_contact(contacts: list[ContactModel]) -> ContactModel | None:
    candidates = [contact for contact in contacts if contact.email]
    if not candidates:
        return None
    status_rank = {
        "valid": 4,
        "risky": 3,
        "unverified": 2,
        "unknown": 1,
        "invalid": 0,
    }
    return max(
        candidates,
        key=lambda contact: (
            status_rank.get(contact.verification_status, 0),
            contact.verification_score or 0,
            contact.last_seen_at,
        ),
    )


def _has_observation(lead: LeadModel, observation_id: str) -> bool:
    return any(
        isinstance(source, dict)
        and source.get("source_observation_id") == observation_id
        for source in lead.raw_sources or []
    )


# Backward-compatible name for callers predating ordinary-search audits.
TerritoryOpportunityAuditor = BusinessOpportunityAuditor
