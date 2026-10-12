from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import SignalDefinitionModel


class SignalDefinitionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, definition_id: str) -> SignalDefinitionModel | None:
        return self.session.get(SignalDefinitionModel, definition_id)

    def get_by_key(self, key: str) -> SignalDefinitionModel | None:
        return self.session.scalar(
            select(SignalDefinitionModel)
            .where(SignalDefinitionModel.key == key)
            .limit(1)
        )

    def list(self, *, status: str | None = None) -> list[SignalDefinitionModel]:
        statement = select(SignalDefinitionModel)
        if status:
            statement = statement.where(SignalDefinitionModel.status == status)
        return list(
            self.session.scalars(
                statement.order_by(
                    SignalDefinitionModel.category,
                    SignalDefinitionModel.label,
                )
            )
        )
