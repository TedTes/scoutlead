from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignCreate, CampaignGoalType
from db.models import AudienceResultModel, AudienceRunModel, TerritoryModel
from leads.repository import LeadRepository
from leads.schemas import LeadRead, LeadReviewStatus, LeadUpdate, QualificationResult
from shared.errors import NotFoundError


class AudienceOutreachService:
    def __init__(self, session: Session, *, workspace_id: str | None) -> None:
        self.session = session
        self.workspace_id = workspace_id

    def promote(self, result_id: str) -> LeadRead:
        result = self.session.scalar(
            select(AudienceResultModel)
            .where(AudienceResultModel.id == result_id)
            .with_for_update()
        )
        if result is None:
            raise NotFoundError("audience result not found", {"result_id": result_id})
        run = self.session.scalar(
            select(AudienceRunModel)
            .where(AudienceRunModel.id == result.run_id)
            .with_for_update()
        )
        audience = self.session.get(TerritoryModel, result.audience_id)
        if (
            run is None
            or audience is None
            or (
                self.workspace_id is not None
                and run.workspace_id != self.workspace_id
            )
        ):
            raise NotFoundError("audience result not found", {"result_id": result_id})
        leads = LeadRepository(self.session, workspace_id=self.workspace_id)
        if result.outreach_lead_id:
            return LeadRead.model_validate(leads.get(result.outreach_lead_id))
        campaign_id = run.outreach_campaign_id
        if campaign_id is None:
            campaign = CampaignRepository(
                self.session,
                workspace_id=self.workspace_id,
            ).create(
                CampaignCreate(
                    product_id=audience.product_id,
                    territory_id=audience.id,
                    name=f"{audience.label} outreach",
                    goal_type=CampaignGoalType.SELL,
                    source_inputs={
                        "audience_run": {
                            "run_id": run.id,
                            "criteria_version": run.criteria_version,
                        }
                    },
                    max_leads=run.requested_count,
                    channels=["email"],
                ),
                commit=False,
            )
            campaign_id = campaign.id
            run.outreach_campaign_id = campaign.id
        lead = leads.create_from_existing_match(
            campaign_id,
            audience.product_id,
            result.match_snapshot,
            commit=False,
        )
        match = (result.match_snapshot.get("raw") or {}).get("profile_match") or {}
        reasons = [
            _signal_reason(item)
            for item in match.get("matched_signals") or []
            if isinstance(item, dict)
        ]
        score = min(
            100,
            80 + max(0, int(match.get("confirmed_signal_count") or 0) - 1) * 5,
        )
        leads.attach_qualification(
            lead.id,
            QualificationResult(
                qualified=True,
                fit_status="good_fit",
                score=score,
                rationale=reasons[0] if reasons else "Matched the saved audience criteria.",
                positive_signals=reasons,
                signal_tags=[
                    str(item.get("signal_key"))
                    for item in match.get("matched_signals") or []
                    if isinstance(item, dict) and item.get("signal_key")
                ],
                recommended_next_step="Review the evidence before outreach.",
            ),
            commit=False,
        )
        review_status = LeadReviewStatus(result.review_status)
        update = LeadUpdate(
            review_status=(
                review_status
                if review_status != LeadReviewStatus.UNREVIEWED
                else LeadReviewStatus.GOOD_FIT
            ),
            review_note=result.review_note,
            shortlisted=result.shortlisted_at is not None,
        )
        lead = leads.update(lead.id, update, commit=False)
        result.outreach_lead_id = lead.id
        self.session.commit()
        self.session.refresh(lead)
        return LeadRead.model_validate(lead)


def _signal_reason(signal: dict) -> str:
    key = str(signal.get("signal_key") or "")
    value = signal.get("value")
    if key == "website_unavailable":
        return "The verified website status is unavailable."
    if key == "reviews_under_15":
        return f"The business has {int(value or 0)} public reviews."
    if key == "no_quote_flow":
        return "No quote or booking flow was found in the stored inspection."
    if key == "no_contact_form":
        return "No contact form was found in the stored inspection."
    return f"Matched {key.replace('_', ' ')}."
