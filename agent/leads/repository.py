from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.embeddings import EmbeddingClient
from campaigns.schemas import LeadSeedInput
from canonical.repository import CanonicalRepository
from db.models import DiscoveryCandidateModel, LeadModel, ProductModel
from leads.policy import can_shortlist_lead, normalize_qualification_result
from leads.schemas import (
    ContactPolicyStatus,
    ContactVerificationStatus,
    LeadContactPolicyUpdate,
    LeadResearch,
    LeadReviewStatus,
    LeadStatus,
    LeadUpdate,
    LeadVerification,
    QualificationResult,
)
from shared.errors import ConflictError, NotFoundError
from shared.utils import new_id, normalize_url, utcnow
from suppressions.repository import ContactSuppressionRepository, is_blocked_contact_policy


class LeadRepository:
    def __init__(
        self,
        session: Session,
        *,
        embedding: EmbeddingClient | None = None,
        workspace_id: str | None = None,
    ) -> None:
        self.session = session
        self.embedding = embedding
        self.workspace_id = workspace_id

    def create_from_seed(self, campaign_id: str, product_id: str, seed: LeadSeedInput) -> LeadModel:
        self._assert_product_in_scope(product_id)
        existing = self.find_existing(campaign_id, seed.company_name, seed.website_url)
        if existing:
            return ContactSuppressionRepository(self.session).apply_to_lead_model(existing)

        canonical = CanonicalRepository(
            self.session,
            embedding=self.embedding,
        ).upsert_from_discovery_result(
            company_name=seed.company_name,
            website_url=seed.website_url,
            contact_email=seed.contact_email,
            geography=seed.geography,
            description=seed.description,
            source=seed.source or "campaign_seed",
            raw=seed.raw or seed.model_dump(mode="json"),
        )
        model = LeadModel(
            id=new_id("lead"),
            campaign_id=campaign_id,
            product_id=product_id,
            business_id=canonical.business_id,
            contact_id=canonical.contact_id,
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
        ContactSuppressionRepository(self.session).apply_to_lead_model(model, commit=False)
        self.session.commit()
        self.session.refresh(model)
        return model

    def create_from_search_result(
        self, campaign_id: str, product_id: str, result: dict[str, Any]
    ) -> LeadModel:
        self._assert_product_in_scope(product_id)
        company_name = result.get("title") or result.get("company_name")
        if not company_name:
            raise ValueError("search result is missing title/company_name")
        existing = self.find_existing(campaign_id, company_name, result.get("url"))
        if existing:
            return ContactSuppressionRepository(self.session).apply_to_lead_model(existing)

        canonical = CanonicalRepository(
            self.session,
            embedding=self.embedding,
        ).upsert_from_discovery_result(
            company_name=company_name,
            website_url=result.get("url") or result.get("website_url"),
            contact_email=result.get("contact_email"),
            geography=result.get("geography"),
            description=result.get("snippet") or result.get("description"),
            source=result.get("provider_id") or result.get("source") or "search",
            raw=result,
        )
        model = LeadModel(
            id=new_id("lead"),
            campaign_id=campaign_id,
            product_id=product_id,
            business_id=canonical.business_id,
            contact_id=canonical.contact_id,
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
        ContactSuppressionRepository(self.session).apply_to_lead_model(model, commit=False)
        self.session.commit()
        self.session.refresh(model)
        return model

    def create_from_candidate(self, candidate: DiscoveryCandidateModel) -> LeadModel:
        self._assert_product_in_scope(candidate.product_id)
        existing = self.find_existing(candidate.campaign_id, candidate.title, candidate.url)
        if existing:
            return ContactSuppressionRepository(self.session).apply_to_lead_model(existing)

        raw_source = {
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
        canonical = CanonicalRepository(
            self.session,
            embedding=self.embedding,
        ).upsert_from_discovery_result(
            company_name=candidate.title,
            website_url=candidate.url,
            contact_email=candidate.contact_email,
            geography=candidate.geography,
            description=candidate.snippet,
            source=candidate.raw.get("provider_id") or candidate.source,
            raw=raw_source,
        )
        model = LeadModel(
            id=new_id("lead"),
            campaign_id=candidate.campaign_id,
            product_id=candidate.product_id,
            business_id=canonical.business_id,
            contact_id=canonical.contact_id,
            company_name=candidate.title,
            website_url=normalize_url(candidate.url),
            contact_email=candidate.contact_email,
            geography=candidate.geography,
            description=candidate.snippet,
            source=candidate.source,
            status=LeadStatus.DISCOVERED.value,
            review_status=LeadReviewStatus.UNREVIEWED.value,
            verification_status=ContactVerificationStatus.UNVERIFIED.value,
            raw_sources=[raw_source],
        )
        self.session.add(model)
        ContactSuppressionRepository(self.session).apply_to_lead_model(model, commit=False)
        self.session.commit()
        self.session.refresh(model)
        return model

    def list_by_campaign(self, campaign_id: str) -> list[LeadModel]:
        statement = (
            select(LeadModel).where(LeadModel.campaign_id == campaign_id).order_by(LeadModel.created_at)
        )
        statement = self._scope(statement)
        return list(self.session.scalars(statement))

    def get(self, lead_id: str) -> LeadModel:
        model = self.session.scalar(self._scope(select(LeadModel).where(LeadModel.id == lead_id)))
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
            if data["shortlisted"] and is_blocked_contact_policy(model.contact_policy_status):
                raise ConflictError(
                    "lead is blocked from outreach",
                    {
                        "lead_id": lead_id,
                        "contact_policy_status": model.contact_policy_status,
                        "user_message": "This contact is marked do-not-contact and cannot be shortlisted.",
                    },
                )
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

    def update_contact_policy(self, lead_id: str, update: LeadContactPolicyUpdate) -> LeadModel:
        model = self.get(lead_id)
        if update.status == ContactPolicyStatus.ALLOWED:
            return ContactSuppressionRepository(self.session).clear_lead_policy(model)
        return ContactSuppressionRepository(self.session).set_lead_policy(
            model,
            status=update.status,
            reason=update.reason,
            scope=update.scope,
        )

    def mark_contacted(self, lead_id: str, contacted_at=None) -> LeadModel:
        model = self.get(lead_id)
        model.last_contacted_at = contacted_at or utcnow()
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
        checked_at = utcnow()
        model.verification_status = result.status.value
        model.verification_provider = result.provider
        model.verification_checked_at = checked_at
        model.verification_reason = result.reason
        model.verification_score = result.score
        model.verification_details = result.details or None
        CanonicalRepository(self.session).apply_contact_verification(
            contact_id=model.contact_id,
            status=model.verification_status,
            provider=model.verification_provider,
            checked_at=checked_at,
            reason=model.verification_reason,
            score=model.verification_score,
            details=model.verification_details,
        )
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

    def _scope(self, statement):
        if not self.workspace_id:
            return statement
        return statement.join(ProductModel, LeadModel.product_id == ProductModel.id).where(
            ProductModel.workspace_id == self.workspace_id
        )

    def _assert_product_in_scope(self, product_id: str) -> None:
        if not self.workspace_id:
            return
        exists = self.session.scalar(
            select(ProductModel.id)
            .where(ProductModel.id == product_id)
            .where(ProductModel.workspace_id == self.workspace_id)
        )
        if not exists:
            raise NotFoundError("product not found", {"product_id": product_id})
