from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import (
    BusinessModel,
    CampaignModel,
    ContactModel,
    LeadModel,
    LeadOutcomeModel,
    ProductModel,
    TerritoryModel,
)
from outcomes.policy import no_response_due
from outcomes.repository import OutcomeRepository
from outcomes.schemas import (
    LeadOutcome,
    LeadOutcomeCreate,
    OutcomeChannel,
    OutcomeSource,
)
from products.repository import DEFAULT_WORKSPACE_ID
from shared.errors import NotFoundError
from shared.utils import new_id, utcnow
from territories.refill import enqueue_refill_if_depleted


class OutcomeService:
    def __init__(
        self,
        session: Session,
        *,
        workspace_id: str | None,
        recorded_by: str | None = None,
    ) -> None:
        self.session = session
        self.workspace_id = workspace_id or DEFAULT_WORKSPACE_ID
        self.recorded_by = recorded_by
        self.repository = OutcomeRepository(session, workspace_id=self.workspace_id)

    def record(self, lead_id: str, data: LeadOutcomeCreate) -> LeadOutcomeModel:
        lead = self._lead(lead_id)
        occurred_at = data.occurred_at or utcnow()
        campaign = self.session.get(CampaignModel, lead.campaign_id)
        territory_id = lead.territory_id or (campaign.territory_id if campaign else None)
        territory = (
            self.session.get(TerritoryModel, territory_id)
            if territory_id
            else None
        )
        model = LeadOutcomeModel(
            id=new_id("outcome"),
            workspace_id=self.workspace_id,
            product_id=lead.product_id,
            lead_id=lead.id,
            business_id=lead.business_id,
            territory_id=territory.id if territory else None,
            niche_id=territory.niche_id if territory else None,
            market_key=territory.market_key if territory else None,
            outcome=data.outcome.value,
            channel=data.channel.value,
            source=data.source.value,
            note=" ".join(data.note.split()) if data.note else None,
            occurred_at=occurred_at,
            recorded_by=self.recorded_by,
        )
        self.session.add(model)
        if lead.latest_outcome_at is None or occurred_at >= _aware(lead.latest_outcome_at):
            lead.latest_outcome = data.outcome.value
            lead.latest_outcome_at = occurred_at
        self._apply_objective_quality_update(lead, data.outcome, occurred_at)
        self.session.commit()
        self.session.refresh(model)
        enqueue_refill_if_depleted(self.session, territory_id)
        self._recompute_learning_model_if_due(model)
        return model

    def list_for_lead(self, lead_id: str) -> list[LeadOutcomeModel]:
        return self.repository.list_for_lead(lead_id)

    def record_due_no_responses(self, *, days: int, now: datetime | None = None) -> int:
        now = now or utcnow()
        leads = list(
            self.session.scalars(
                select(LeadModel)
                .join(ProductModel, LeadModel.product_id == ProductModel.id)
                .where(
                    ProductModel.workspace_id == self.workspace_id,
                    LeadModel.latest_outcome == LeadOutcome.CONTACTED.value,
                    LeadModel.latest_outcome_at.is_not(None),
                )
            )
        )
        recorded = 0
        for lead in leads:
            if no_response_due(
                contacted_at=_aware(lead.latest_outcome_at),
                latest_outcome=lead.latest_outcome,
                now=_aware(now),
                days=days,
            ):
                self.record(
                    lead.id,
                    LeadOutcomeCreate(
                        outcome=LeadOutcome.NO_RESPONSE,
                        channel=OutcomeChannel.EMAIL,
                        source=OutcomeSource.SYSTEM,
                        occurred_at=now,
                    ),
                )
                recorded += 1
        return recorded

    def _lead(self, lead_id: str) -> LeadModel:
        lead = self.session.scalar(
            select(LeadModel)
            .join(ProductModel, LeadModel.product_id == ProductModel.id)
            .where(LeadModel.id == lead_id, ProductModel.workspace_id == self.workspace_id)
        )
        if lead is None:
            raise NotFoundError("lead not found", {"lead_id": lead_id})
        return lead

    def _apply_objective_quality_update(
        self,
        lead: LeadModel,
        outcome: LeadOutcome,
        occurred_at: datetime,
    ) -> None:
        if outcome in {LeadOutcome.BOUNCED, LeadOutcome.WRONG_CONTACT}:
            lead.verification_status = "invalid"
            lead.verification_checked_at = occurred_at
            lead.verification_reason = outcome.value.replace("_", " ")
            if lead.contact_id:
                contact = self.session.get(ContactModel, lead.contact_id)
                if contact:
                    contact.verification_status = "invalid"
                    contact.verification_checked_at = occurred_at
                    contact.verification_reason = lead.verification_reason
        if outcome == LeadOutcome.BUSINESS_CLOSED and lead.business_id:
            business = self.session.get(BusinessModel, lead.business_id)
            if business:
                business.status = "closed"

    def _recompute_learning_model_if_due(self, outcome: LeadOutcomeModel) -> None:
        if not outcome.niche_id:
            return
        outcome_count = len(
            self.session.scalars(
                select(LeadOutcomeModel.id).where(
                    LeadOutcomeModel.workspace_id == self.workspace_id,
                    LeadOutcomeModel.product_id == outcome.product_id,
                    LeadOutcomeModel.niche_id == outcome.niche_id,
                )
            ).all()
        )
        if outcome_count % 10:
            return
        from evaluation.outcome_learning_service import OutcomeLearningService

        OutcomeLearningService(self.session, workspace_id=self.workspace_id).recompute(
            product_id=outcome.product_id,
            niche_id=outcome.niche_id,
        )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
