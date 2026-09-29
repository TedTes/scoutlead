from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import TerritoryDeliveryModel, TerritoryModel
from shared.errors import ConflictError, NotFoundError
from shared.utils import new_id, utcnow
from territories.schemas import TerritoryCreate, TerritoryUpdate


class TerritoryRepository:
    def __init__(self, session: Session, *, workspace_id: str) -> None:
        self.session = session
        self.workspace_id = workspace_id

    def create(self, data: TerritoryCreate, *, niche_id: str) -> TerritoryModel:
        existing = self.session.scalar(
            self._scope(
                select(TerritoryModel).where(
                    TerritoryModel.product_id == data.product_id,
                    TerritoryModel.niche_id == niche_id,
                    TerritoryModel.market_key == data.market_key,
                )
            ).limit(1)
        )
        if existing is not None:
            raise ConflictError(
                "territory already exists for this offer, niche, and market",
                {"territory_id": existing.id},
            )
        model = TerritoryModel(
            id=new_id("territory"),
            workspace_id=self.workspace_id,
            product_id=data.product_id,
            niche_id=niche_id,
            market_key=data.market_key,
            label=data.label or f"{data.niche_label} · {data.market_key}",
            status=data.status.value,
            cadence=data.cadence.value,
            batch_size=data.batch_size,
            min_fit=data.min_fit.value,
            next_run_at=utcnow(),
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return model

    def list(self) -> list[TerritoryModel]:
        return list(
            self.session.scalars(
                self._scope(select(TerritoryModel)).order_by(TerritoryModel.created_at.desc())
            )
        )

    def get(self, territory_id: str) -> TerritoryModel:
        model = self.session.scalar(
            self._scope(select(TerritoryModel).where(TerritoryModel.id == territory_id))
        )
        if model is None:
            raise NotFoundError("territory not found", {"territory_id": territory_id})
        return model

    def update(self, territory_id: str, update: TerritoryUpdate) -> TerritoryModel:
        model = self.get(territory_id)
        for field, value in update.model_dump(mode="python", exclude_unset=True).items():
            setattr(model, field, value.value if hasattr(value, "value") else value)
        model.updated_at = utcnow()
        self.session.commit()
        self.session.refresh(model)
        return model

    def delete(self, territory_id: str) -> None:
        model = self.get(territory_id)
        has_delivery = self.session.scalar(
            select(TerritoryDeliveryModel.id)
            .where(TerritoryDeliveryModel.territory_id == territory_id)
            .limit(1)
        )
        if has_delivery:
            raise ConflictError(
                "territories with delivery history must be paused instead of deleted",
                {"territory_id": territory_id},
            )
        self.session.delete(model)
        self.session.commit()

    def list_deliveries(self, territory_id: str) -> list[TerritoryDeliveryModel]:
        self.get(territory_id)
        statement = (
            select(TerritoryDeliveryModel)
            .where(
                TerritoryDeliveryModel.workspace_id == self.workspace_id,
                TerritoryDeliveryModel.territory_id == territory_id,
            )
            .order_by(TerritoryDeliveryModel.created_at.desc())
        )
        return list(self.session.scalars(statement))

    def get_delivery(self, territory_id: str, delivery_id: str) -> TerritoryDeliveryModel:
        self.get(territory_id)
        model = self.session.scalar(
            select(TerritoryDeliveryModel).where(
                TerritoryDeliveryModel.id == delivery_id,
                TerritoryDeliveryModel.territory_id == territory_id,
                TerritoryDeliveryModel.workspace_id == self.workspace_id,
            )
        )
        if model is None:
            raise NotFoundError("territory delivery not found", {"delivery_id": delivery_id})
        return model

    def delivery_for_schedule(
        self,
        territory_id: str,
        scheduled_for: datetime,
    ) -> TerritoryDeliveryModel | None:
        return self.session.scalar(
            select(TerritoryDeliveryModel).where(
                TerritoryDeliveryModel.workspace_id == self.workspace_id,
                TerritoryDeliveryModel.territory_id == territory_id,
                TerritoryDeliveryModel.scheduled_for == scheduled_for,
            )
        )

    def _scope(self, statement):
        return statement.where(TerritoryModel.workspace_id == self.workspace_id)
