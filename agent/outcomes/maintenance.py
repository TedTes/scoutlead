from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import LeadOutcomeModel, WorkspaceModel
from evaluation.outcome_learning_service import OutcomeLearningService
from outcomes.service import OutcomeService


def run_outcome_maintenance(session: Session, *, no_response_days: int) -> None:
    for workspace_id in session.scalars(select(WorkspaceModel.id)):
        OutcomeService(session, workspace_id=workspace_id).record_due_no_responses(
            days=no_response_days
        )

    dimensions = set(
        session.execute(
            select(
                LeadOutcomeModel.workspace_id,
                LeadOutcomeModel.product_id,
                LeadOutcomeModel.niche_id,
            ).where(LeadOutcomeModel.niche_id.is_not(None))
        ).all()
    )
    for workspace_id, product_id, niche_id in dimensions:
        OutcomeLearningService(session, workspace_id=workspace_id).recompute(
            product_id=product_id,
            niche_id=niche_id,
        )
