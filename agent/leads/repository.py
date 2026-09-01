from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from campaigns.schemas import LeadSeedInput
from db.models import DiscoveryCandidateModel, LeadModel
from leads.policy import can_shortlist_lead, normalize_qualification_result
from leads.schemas import (
    ContactVerificationStatus,
    LeadResearch,
    LeadReviewStatus,
    LeadStatus,
    LeadUpdate,
    LeadVerification,
    QualificationResult,
)
from shared.errors import ConflictError, NotFoundError
from shared.utils import new_id, normalize_url, utcnow


class LeadRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_from_seed(self, campaign_id: str, product_id: str, seed: LeadSeedInput) -> LeadModel:
        existing = self.find_existing(campaign_id, seed.company_name, seed.website_url)
        if existing:
            return existing

        model = LeadModel(
            id=new_id("lead"),
            campaign_id=campaign_id,
            product_id=product_id,
            company_name=seed.company_name,
            website_url=normalize_url(seed.website_url),
            contact_email=seed.contact_email,
            geography=seed.geography,
            description=seed.description,
            source=seed.source or "campaign_seed",
            status=LeadStatus.DISCOVERED.value,
            review_status=LeadReviewStatus.UNREVIEWED.value,
            verification_status=ContactVerificationStatus.UNVERIFIED.value,
            raw_sources=[seed.raw or seed.model_dump(mode="json")],
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return model

    def create_from_search_result(
        self, campaign_id: str, product_id: str, result: dict[str, Any]
    ) -> LeadModel:
        company_name = result.get("title") or result.get("company_name")
        if not company_name:
            raise ValueError("search result is missing title/company_name")
        existing = self.find_existing(campaign_id, company_name, result.get("url"))
        if existing:
            return existing

        model = LeadModel(
            id=new_id("lead"),
            campaign_id=campaign_id,
            product_id=product_id,
            company_name=company_name,
            website_url=normalize_url(result.get("url") or result.get("website_url")),
            contact_email=result.get("contact_email"),
            geography=result.get("geography"),
            description=result.get("snippet") or result.get("description"),
            source=result.get("source") or "search",
            status=LeadStatus.DISCOVERED.value,
            review_status=LeadReviewStatus.UNREVIEWED.value,
            verification_status=ContactVerificationStatus.UNVERIFIED.value,
            raw_sources=[result],
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return model

    def create_from_candidate(self, candidate: DiscoveryCandidateModel) -> LeadModel:
        existing = self.find_existing(candidate.campaign_id, candidate.title, candidate.url)
        if existing:
            return existing

        model = LeadModel(
            id=new_id("lead"),
            campaign_id=candidate.campaign_id,
            product_id=candidate.product_id,
            company_name=candidate.title,
            website_url=normalize_url(candidate.url),
            contact_email=candidate.contact_email,
            geography=candidate.geography,
            description=candidate.snippet,
            source=candidate.source,
            status=LeadStatus.DISCOVERED.value,
            review_status=LeadReviewStatus.UNREVIEWED.value,
            verification_status=ContactVerificationStatus.UNVERIFIED.value,
            raw_sources=[
                {
                    "candidate_id": candidate.id,
                    "query": candidate.query,
                    "title": candidate.title,
                    "url": candidate.url,
                    "snippet": candidate.snippet,
                    "geography": candidate.geography,
                    "contact_email": candidate.contact_email,
                    "source": candidate.source,
                    "candidate_type": candidate.candidate_type,
                    "confidence": candidate.confidence,
                    "raw": candidate.raw,
                }
            ],
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return model

    def list_by_campaign(self, campaign_id: str) -> list[LeadModel]:
        statement = (
            select(LeadModel).where(LeadModel.campaign_id == campaign_id).order_by(LeadModel.created_at)
        )
        return list(self.session.scalars(statement))

    def get(self, lead_id: str) -> LeadModel:
        model = self.session.get(LeadModel, lead_id)
        if model is None:
            raise NotFoundError("lead not found", {"lead_id": lead_id})
        return model

    def update_status(self, lead_id: str, status: LeadStatus) -> LeadModel:
        model = self.get(lead_id)
        model.status = status.value
        self.session.commit()
        self.session.refresh(model)
        return model

    def update(self, lead_id: str, update: LeadUpdate) -> LeadModel:
        model = self.get(lead_id)
        data = update.model_dump(mode="python", exclude_unset=True)
        next_review_status = LeadReviewStatus(model.review_status)
        if "review_status" in data:
            status = data["review_status"]
            next_review_status = status if isinstance(status, LeadReviewStatus) else LeadReviewStatus(status)
            model.review_status = next_review_status.value
            model.reviewed_at = utcnow()
            if next_review_status == LeadReviewStatus.NOT_FIT:
                model.shortlisted_at = None
        if "review_note" in data:
            note = data["review_note"]
            model.review_note = note.strip() if isinstance(note, str) and note.strip() else None
        if "shortlisted" in data:
            if data["shortlisted"] and not can_shortlist_lead(
                review_status=next_review_status,
                qualification=model.qualification,
            ):
                raise ConflictError(
                    "lead needs a positive fit decision before shortlist",
                    {
                        "lead_id": lead_id,
                        "review_status": next_review_status.value,
                        "user_message": "Mark this contact as Good fit or Maybe before shortlisting.",
                    },
                )
            model.shortlisted_at = utcnow() if data["shortlisted"] else None
        self.session.commit()
        self.session.refresh(model)
        return model

    def attach_research(self, lead_id: str, research: LeadResearch) -> LeadModel:
        model = self.get(lead_id)
        model.research = research.model_dump(mode="json")
        model.website_url = normalize_url(research.website_url) or model.website_url
        model.contact_email = research.contact_email or model.contact_email
        model.geography = research.geography or model.geography
        model.status = LeadStatus.RESEARCHED.value
        self.session.commit()
        self.session.refresh(model)
        return model

    def attach_qualification(self, lead_id: str, result: QualificationResult) -> LeadModel:
        model = self.get(lead_id)
        normalized = normalize_qualification_result(result)
        model.qualification = normalized.model_dump(mode="json")
        model.status = LeadStatus.QUALIFIED.value if normalized.qualified else LeadStatus.DISQUALIFIED.value
        self.session.commit()
        self.session.refresh(model)
        return model

    def attach_verification(self, lead_id: str, result: LeadVerification) -> LeadModel:
        model = self.get(lead_id)
        model.verification_status = result.status.value
        model.verification_provider = result.provider
        model.verification_checked_at = utcnow()
        model.verification_reason = result.reason
        model.verification_score = result.score
        self.session.commit()
        self.session.refresh(model)
        return model

    def find_existing(
        self, campaign_id: str, company_name: str, website_url: str | None = None
    ) -> LeadModel | None:
        leads = self.list_by_campaign(campaign_id)
        normalized_name = company_name.strip().lower()
        normalized_url = normalize_url(website_url)
        for lead in leads:
            if lead.company_name.strip().lower() == normalized_name:
                return lead
            if normalized_url and lead.website_url == normalized_url:
                return lead
        return None
