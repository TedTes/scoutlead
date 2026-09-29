from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import LeadOutcomeModel, ProductModel
from shared.errors import NotFoundError


class OutcomeRepository:
    def __init__(self, session: Session, *, workspace_id: str) -> None:
        self.session = session
        self.workspace_id = workspace_id

    def list_for_lead(self, lead_id: str) -> list[LeadOutcomeModel]:
        self._assert_lead_in_scope(lead_id)
        return list(
            self.session.scalars(
                select(LeadOutcomeModel)
                .where(
                    LeadOutcomeModel.workspace_id == self.workspace_id,
                    LeadOutcomeModel.lead_id == lead_id,
                )
                .order_by(
                    LeadOutcomeModel.occurred_at.desc(),
                    LeadOutcomeModel.created_at.desc(),
                )
            )
        )

    def _assert_lead_in_scope(self, lead_id: str) -> None:
        from db.models import LeadModel

        exists = self.session.scalar(
            select(LeadModel.id)
            .join(ProductModel, LeadModel.product_id == ProductModel.id)
            .where(LeadModel.id == lead_id, ProductModel.workspace_id == self.workspace_id)
        )
        if not exists:
            raise NotFoundError("lead not found", {"lead_id": lead_id})
