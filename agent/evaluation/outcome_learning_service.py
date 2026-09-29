from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import LeadModel, LeadOutcomeModel, OutcomeModel, TerritoryModel
from evaluation.outcome_learning import (
    OutcomeSample,
    adjusted_rank_score,
    compute_outcome_weights,
    outcome_adjustment,
)
from leads.schemas import AgentFitStatus
from outcomes.policy import POSITIVE_OUTCOMES
from outcomes.schemas import LeadOutcome
from shared.utils import new_id, utcnow


class OutcomeLearningService:
    def __init__(self, session: Session, *, workspace_id: str) -> None:
        self.session = session
        self.workspace_id = workspace_id

    def recompute(self, *, product_id: str, niche_id: str) -> OutcomeModel:
        outcomes = list(
            self.session.scalars(
                select(LeadOutcomeModel)
                .where(
                    LeadOutcomeModel.workspace_id == self.workspace_id,
                    LeadOutcomeModel.product_id == product_id,
                    LeadOutcomeModel.niche_id == niche_id,
                )
                .order_by(LeadOutcomeModel.occurred_at)
            )
        )
        by_lead: dict[str, list[LeadOutcomeModel]] = defaultdict(list)
        for outcome in outcomes:
            by_lead[outcome.lead_id].append(outcome)
        samples: list[OutcomeSample] = []
        for lead_id, events in by_lead.items():
            event_types = {LeadOutcome(event.outcome) for event in events}
            if LeadOutcome.CONTACTED not in event_types:
                continue
            lead = self.session.get(LeadModel, lead_id)
            qualification = lead.qualification if lead and isinstance(lead.qualification, dict) else {}
            samples.append(
                OutcomeSample(
                    signal_tags=tuple(qualification.get("signal_tags") or []),
                    positive=bool(event_types & POSITIVE_OUTCOMES),
                )
            )
        computed = compute_outcome_weights(samples)
        model = self.session.scalar(
            select(OutcomeModel).where(
                OutcomeModel.workspace_id == self.workspace_id,
                OutcomeModel.product_id == product_id,
                OutcomeModel.niche_id == niche_id,
            )
        )
        if model is None:
            model = OutcomeModel(
                id=new_id("outcome_model"),
                workspace_id=self.workspace_id,
                product_id=product_id,
                niche_id=niche_id,
                computed_at=utcnow(),
                n_contacted=computed.n_contacted,
                n_positive=computed.n_positive,
                weights=computed.weights,
            )
            self.session.add(model)
        else:
            model.computed_at = utcnow()
            model.n_contacted = computed.n_contacted
            model.n_positive = computed.n_positive
            model.weights = computed.weights
        self._apply(product_id=product_id, niche_id=niche_id, weights=computed.weights)
        self.session.commit()
        self.session.refresh(model)
        return model

    def _apply(self, *, product_id: str, niche_id: str, weights: dict[str, float]) -> None:
        lead_ids = set(
            self.session.scalars(
                select(LeadModel.id)
                .join(TerritoryModel, LeadModel.territory_id == TerritoryModel.id)
                .where(
                    LeadModel.product_id == product_id,
                    TerritoryModel.workspace_id == self.workspace_id,
                    TerritoryModel.niche_id == niche_id,
                )
            )
        )
        for lead_id in lead_ids:
            lead = self.session.get(LeadModel, lead_id)
            qualification = lead.qualification if lead and isinstance(lead.qualification, dict) else None
            if not lead or not qualification:
                continue
            fit_status = qualification.get("fit_status") or AgentFitStatus.NOT_FIT.value
            breakdown = qualification.get("score_breakdown") or {}
            fit_score = float(breakdown.get("fit_score", qualification.get("score", 0)))
            adjustment = outcome_adjustment(
                qualification.get("signal_tags") or [],
                weights,
            )
            if fit_status == AgentFitStatus.NOT_FIT.value:
                adjustment = 0.0
            lead.outcome_adjustment = adjustment
            lead.rank_score = adjusted_rank_score(
                fit_score=fit_score,
                fit_status=fit_status,
                adjustment=adjustment,
            )
