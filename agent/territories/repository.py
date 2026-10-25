from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import TerritoryModel
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
        reuse_existing: bool = False,
        allow_duplicate: bool = False,
        commit: bool = True,
    ) -> TerritoryModel:
        existing = None
        if not allow_duplicate:
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
                existing.place_label = data.place_label
                existing.place_provider = data.place_provider
                existing.place_external_id = data.place_external_id
                existing.country_code = data.country_code
                existing.latitude = data.latitude
                existing.longitude = data.longitude
                existing.radius_km = data.radius_km
                existing.customer_kind = data.customer_kind.value
                existing.service_keys = data.service_keys
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
            if reuse_existing:
                return existing
            raise ConflictError(
                "territory already exists for this offer, niche, and market",
                {"territory_id": existing.id},
            )
        model = TerritoryModel(
            id=new_id("territory"),
            workspace_id=self.workspace_id,
            product_id=data.product_id,
            folder_id=data.folder_id,
            niche_id=niche_id,
            market_key=data.market_key,
            city=data.city or data.market_key,
            place_label=data.place_label,
            place_provider=data.place_provider,
            place_external_id=data.place_external_id,
            country_code=data.country_code,
            latitude=data.latitude,
            longitude=data.longitude,
            radius_km=data.radius_km,
            customer_kind=data.customer_kind.value,
            service_keys=data.service_keys,
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

    def _scope(self, statement):
        return statement.where(TerritoryModel.workspace_id == self.workspace_id)
