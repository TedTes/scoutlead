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

    def create(
        self,
        data: TerritoryCreate,
        *,
        niche_id: str,
        commit: bool = True,
    ) -> TerritoryModel:
        existing = self.session.scalar(
            self._scope(
                select(TerritoryModel).where(
                    TerritoryModel.product_id == data.product_id,
                    TerritoryModel.niche_id == niche_id,
                    TerritoryModel.market_key == data.market_key,
                    TerritoryModel.criteria_hash == data.criteria_hash,
                )
            ).limit(1)
        )
        if existing is not None:
            if existing.status == "archived":
                existing.city = data.city or data.market_key
                existing.latitude = data.latitude
                existing.longitude = data.longitude
                existing.radius_km = data.radius_km
                existing.trade_keys = data.trade_keys
                existing.customer_kind = data.customer_kind.value
                existing.signal_keys = data.signal_keys
                existing.exclusion_keys = data.exclusion_keys
                existing.status = data.status.value
                existing.label = data.label or f"{data.niche_label} · {data.market_key}"
                existing.cadence = data.cadence.value
                existing.refill_policy = data.refill_policy.value
                existing.criteria_version = data.criteria_version
                existing.batch_size = data.batch_size
                existing.min_fit = data.min_fit.value
                existing.search_prompt = data.request
                existing.search_contract = data.search_contract
                existing.evidence_max_age_days = data.evidence_max_age_days
                existing.next_run_at = utcnow()
                existing.updated_at = utcnow()
                if commit:
                    self.session.commit()
                else:
                    self.session.flush()
                self.session.refresh(existing)
                return existing
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
            city=data.city or data.market_key,
            latitude=data.latitude,
            longitude=data.longitude,
            radius_km=data.radius_km,
            trade_keys=data.trade_keys,
            customer_kind=data.customer_kind.value,
            signal_keys=data.signal_keys,
            exclusion_keys=data.exclusion_keys,
            label=data.label or f"{data.niche_label} · {data.market_key}",
            status=data.status.value,
            cadence=data.cadence.value,
            refill_policy=data.refill_policy.value,
            criteria_version=data.criteria_version,
            batch_size=data.batch_size,
            min_fit=data.min_fit.value,
            search_prompt=data.request,
            search_contract=data.search_contract,
            evidence_max_age_days=data.evidence_max_age_days,
            criteria_hash=data.criteria_hash,
            next_run_at=utcnow(),
        )
        self.session.add(model)
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        self.session.refresh(model)
        return model

    def list(self) -> list[TerritoryModel]:
        return list(
            self.session.scalars(
                self._scope(
                    select(TerritoryModel).where(TerritoryModel.status != "archived")
                ).order_by(TerritoryModel.created_at.desc())
            )
        )

    def get(self, territory_id: str) -> TerritoryModel:
        model = self.session.scalar(
            self._scope(select(TerritoryModel).where(TerritoryModel.id == territory_id))
        )
        if model is None:
            raise NotFoundError("territory not found", {"territory_id": territory_id})
        return model

    def update(
        self,
        territory_id: str,
        update: TerritoryUpdate,
        *,
        commit: bool = True,
    ) -> TerritoryModel:
        model = self.get(territory_id)
        for field, value in update.model_dump(mode="python", exclude_unset=True).items():
            if isinstance(value, list):
                value = [item.value if hasattr(item, "value") else item for item in value]
            setattr(model, field, value.value if hasattr(value, "value") else value)
        model.updated_at = utcnow()
        if commit:
            self.session.commit()
            self.session.refresh(model)
        else:
            self.session.flush()
        return model

    def delete(self, territory_id: str) -> None:
        model = self.get(territory_id)
        model.status = "archived"
        model.next_run_at = None
        model.updated_at = utcnow()
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

    def latest_delivery(self, territory_id: str) -> TerritoryDeliveryModel | None:
        self.get(territory_id)
        return self.session.scalar(
            select(TerritoryDeliveryModel)
            .where(
                TerritoryDeliveryModel.workspace_id == self.workspace_id,
                TerritoryDeliveryModel.territory_id == territory_id,
            )
            .order_by(TerritoryDeliveryModel.created_at.desc())
            .limit(1)
        )

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
