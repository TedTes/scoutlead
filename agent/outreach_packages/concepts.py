from __future__ import annotations

from datetime import timedelta
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import AudienceResultModel, AudienceRunModel, BusinessModel, LeadConceptModel
from outreach_packages.schemas import LeadConceptRead, LeadConceptUpsert
from shared.errors import NotFoundError, ValidationError, WorkflowBoundaryError
from shared.utils import new_id, normalize_text, utcnow


class LeadConceptService:
    def __init__(self, session: Session, *, workspace_id: str | None) -> None:
        self.session = session
        self.workspace_id = workspace_id

    def find_for_result(self, result_id: str) -> LeadConceptRead | None:
        result, _, business = self._context(result_id)
        row = self.session.scalar(
            select(LeadConceptModel).where(
                LeadConceptModel.workspace_id == self.workspace_id,
                LeadConceptModel.business_id == business.id,
            )
        )
        return self._read(row, business) if row is not None else None

    def upsert(self, result_id: str, data: LeadConceptUpsert) -> LeadConceptRead:
        result, _, business = self._context(result_id)
        if result.shortlisted_at is None:
            raise WorkflowBoundaryError(
                "Shortlist this business before adding a concept.",
                {"result_id": result_id},
            )
        concept_url = _clean_url(data.concept_url, field="concept_url")
        features = [
            value
            for value in (normalize_text(item) for item in data.feature_highlights)
            if value
        ][:5]
        note = normalize_text(data.personalization_note)
        message = data.instagram_message.strip()
        follow_up = data.follow_up_message.strip()
        call_opener = data.call_opener.strip()
        safeguards = {
            "concept_banner_confirmed": data.concept_banner_confirmed,
            "noindex_confirmed": data.noindex_confirmed,
        }
        row = self.session.scalar(
            select(LeadConceptModel).where(
                LeadConceptModel.workspace_id == self.workspace_id,
                LeadConceptModel.business_id == business.id,
            )
        )
        status = _status(concept_url, message, safeguards)
        if row is None:
            row = LeadConceptModel(
                id=new_id("lead_concept"),
                workspace_id=str(self.workspace_id),
                business_id=business.id,
                source_result_id=result.id,
                concept_type=data.concept_type,
                status=status,
                concept_url=concept_url,
                personalization_note=note or None,
                feature_highlights=features,
                safeguards=safeguards,
                instagram_message=message,
                follow_up_message=follow_up,
                call_opener=call_opener,
            )
            self.session.add(row)
        else:
            row.source_result_id = result.id
            row.concept_type = data.concept_type
            row.status = (
                "sent" if row.sent_at is not None and status == "ready" else status
            )
            row.concept_url = concept_url
            row.personalization_note = note or None
            row.feature_highlights = features
            row.safeguards = safeguards
            row.instagram_message = message
            row.follow_up_message = follow_up
            row.call_opener = call_opener
        self.session.commit()
        self.session.refresh(row)
        return self._read(row, business)

    def mark_sent(self, result_id: str) -> LeadConceptRead:
        _, _, business = self._context(result_id)
        row = self.session.scalar(
            select(LeadConceptModel).where(
                LeadConceptModel.workspace_id == self.workspace_id,
                LeadConceptModel.business_id == business.id,
            )
        )
        if row is None:
            raise NotFoundError("lead concept not found", {"result_id": result_id})
        if _status(row.concept_url, row.instagram_message, row.safeguards or {}) != "ready":
            raise WorkflowBoundaryError(
                "Confirm the concept banner and noindex setting before marking outreach sent.",
                {"result_id": result_id},
            )
        now = utcnow()
        row.status = "sent"
        row.sent_at = now
        row.follow_up_due_at = now + timedelta(days=5)
        self.session.commit()
        self.session.refresh(row)
        return self._read(row, business)

    def _context(
        self, result_id: str
    ) -> tuple[AudienceResultModel, AudienceRunModel, BusinessModel]:
        result = self.session.get(AudienceResultModel, result_id)
        run = self.session.get(AudienceRunModel, result.run_id) if result else None
        business = (
            self.session.get(BusinessModel, result.business_id) if result else None
        )
        if (
            result is None
            or run is None
            or business is None
            or not self.workspace_id
            or run.workspace_id != self.workspace_id
        ):
            raise NotFoundError("audience result not found", {"result_id": result_id})
        return result, run, business

    @staticmethod
    def _read(row: LeadConceptModel, business: BusinessModel) -> LeadConceptRead:
        safeguards = row.safeguards or {}
        return LeadConceptRead(
            id=row.id,
            workspace_id=row.workspace_id,
            business_id=row.business_id,
            source_result_id=row.source_result_id,
            business_name=business.display_name,
            concept_type=row.concept_type,
            status=row.status,
            concept_url=row.concept_url,
            personalization_note=row.personalization_note,
            feature_highlights=list(row.feature_highlights or []),
            concept_banner_confirmed=safeguards.get("concept_banner_confirmed") is True,
            noindex_confirmed=safeguards.get("noindex_confirmed") is True,
            instagram_message=row.instagram_message,
            follow_up_message=row.follow_up_message,
            call_opener=row.call_opener,
            sent_at=row.sent_at,
            follow_up_due_at=row.follow_up_due_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


def _clean_url(value: str | None, *, field: str) -> str | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValidationError(
            f"{field.replace('_', ' ')} must be a complete http or https URL."
        )
    return cleaned


def _status(concept_url: str | None, instagram_message: str, safeguards: dict) -> str:
    return (
        "ready"
        if concept_url
        and instagram_message
        and safeguards.get("concept_banner_confirmed") is True
        and safeguards.get("noindex_confirmed") is True
        else "draft"
    )
