from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import WorkspaceModel
from outcomes.service import OutcomeService


def run_outcome_maintenance(session: Session, *, no_response_days: int) -> None:
    for workspace_id in session.scalars(select(WorkspaceModel.id)):
        OutcomeService(session, workspace_id=workspace_id).record_due_no_responses(
            days=no_response_days
        )

    # Learned outcome-model rows were retired. Outcomes remain the durable
    # source data and can be aggregated when there is enough real volume.
