from __future__ import annotations

import hashlib
import json
import re
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from canonical.semantics import semantic_key
from business_index.schemas import OpportunityType, SearchContract
from db.models import LeadOutcomeModel, NicheModel
from outcomes.policy import POSITIVE_OUTCOMES
from outcomes.schemas import LeadOutcome
from niches.resolver import resolve_niche
from products.repository import DEFAULT_WORKSPACE_ID, ProductRepository
from shared.errors import NotFoundError, ValidationError
from shared.utils import new_id, normalize_text, utcnow
from territories.profile_catalog import (
    PROFILE_TRADE_CATALOG,
    profile_trade_label,
    profile_trade_spec,
)
from territories.markets import market_center
from territories.repository import TerritoryRepository
from territories.schemas import (
    ProfileCreate,
    TerritoryCreate,
    TerritoryResolveRequest,
    TerritoryResolutionRead,
    TerritoryRead,
    TerritoryUpdate,
)


class TerritoryService:
    def __init__(self, session: Session, *, workspace_id: str | None) -> None:
        self.session = session
        self.workspace_id = workspace_id or DEFAULT_WORKSPACE_ID
        self.products = ProductRepository(session, workspace_id=self.workspace_id)
        self.territories = TerritoryRepository(session, workspace_id=self.workspace_id)

    def resolve(self, request: TerritoryResolveRequest) -> TerritoryResolutionRead:
        product = self.products.get(request.product_id)
        category, market_label = parse_territory_request(
            request.request,
            default_market=product.target_geography,
        )
        market_key = semantic_key(market_label) or "unknown"
        source_inputs = {
            "query": request.request,
            "source_request_intent": {
                "business_category": category,
                "location": market_label,
                "search_query": request.request,
            },
        }
        resolved = resolve_niche(
            self.session,
            source_inputs=source_inputs,
            source_input=request.request,
        )
        if resolved is not None:
            niche = self.session.get(NicheModel, resolved.niche_id)
            if niche is None:
                raise NotFoundError("resolved niche not found", {"niche_id": resolved.niche_id})
            return TerritoryResolutionRead(
                product_id=product.id,
                request=request.request,
                niche_id=niche.id,
                niche_slug=niche.slug,
                niche_label=niche.label,
                niche_category=niche.category or category,
                market_key=market_key,
                market_label=market_label,
                confidence=resolved.score,
                existing_niche=True,
            )

        label = _title_label(category)
        return TerritoryResolutionRead(
            product_id=product.id,
            request=request.request,
            niche_slug=_slug(category),
            niche_label=label,
            niche_category=category,
            market_key=market_key,
            market_label=market_label,
            confidence=0.5,
            existing_niche=False,
        )

    def create(
        self,
        data: TerritoryCreate,
        *,
        reuse_existing: bool = False,
        commit: bool = True,
    ):
        if not data.confirmed:
            raise ValidationError("territory resolution must be confirmed before creation")
        niche = self._confirmed_niche(data)
        is_profile = bool(data.trade_keys)
        contract_payload = (
            {}
            if is_profile
            else data.search_contract
            or {
                "opportunity_type": OpportunityType.ANY.value,
                "search_contract": SearchContract().as_dict(),
            }
        )
        stored_contract_hash = str(contract_payload.get("contract_hash") or "").strip()
        if is_profile:
            criteria_hash = (
                data.criteria_hash
                if data.criteria_hash != "default"
                else _criteria_hash(_structured_profile_criteria(data))
            )
        else:
            criteria_hash = stored_contract_hash or (
                data.criteria_hash
                if data.criteria_hash != "default"
                else _criteria_hash(contract_payload)
            )
        normalized = data.model_copy(
            update={
                "niche_slug": niche.slug,
                "niche_label": niche.label,
                "market_key": semantic_key(data.market_key) or "unknown",
                "city": normalize_text(data.city or data.market_key),
                "signal_keys": (
                    _clean_profile_keys(data.signal_keys)
                    if data.trade_keys
                    else _clean_keys(data.signal_keys)
                ),
                "exclusion_keys": (
                    _clean_profile_keys(data.exclusion_keys)
                    if data.trade_keys
                    else _clean_keys(data.exclusion_keys)
                ),
                "search_contract": contract_payload,
                "criteria_hash": criteria_hash,
            }
        )
        return self.territories.create(
            normalized,
            niche_id=niche.id,
            reuse_existing=reuse_existing,
            commit=commit,
        )

    def create_profile(self, data: ProfileCreate, *, commit: bool = True):
        trade_keys = list(dict.fromkeys(trade.value for trade in data.trades))
        city = normalize_text(data.market.city)
        niches = [self._ensure_profile_niche(key, city=city) for key in trade_keys]
        trade_label = profile_trade_label(trade_keys)
        customer_kind = data.customer_kind.value
        center = market_center(city)
        if center is None:
            raise ValidationError(
                "market coordinates are unavailable",
                {
                    "city": city,
                    "reason": "A profile radius requires a stored market center.",
                },
            )
        signals = [signal.value for signal in data.signals]
        exclusions = [exclusion.value for exclusion in data.exclude]
        criteria = {
            "trades": trade_keys,
            "customer_kind": customer_kind,
            "city": semantic_key(city),
            "radius_km": data.market.radius_km,
            "signals": signals,
            "exclude": exclusions,
            "limit": data.limit,
            "exclude_already_delivered": True,
        }
        profile = self.create(
            TerritoryCreate(
                product_id=data.product_id,
                niche_id=niches[0].id,
                niche_slug=niches[0].slug,
                niche_label=niches[0].label,
                niche_category=niches[0].category,
                market_key=city,
                city=city,
                latitude=center[0] if center else None,
                longitude=center[1] if center else None,
                radius_km=data.market.radius_km,
                trade_keys=trade_keys,
                customer_kind=data.customer_kind,
                signal_keys=signals,
                exclusion_keys=exclusions,
                label=data.name or f"{trade_label} · {city}",
                refill_policy="when_depleted",
                batch_size=data.limit,
                criteria_hash=_criteria_hash(criteria),
                confirmed=True,
            ),
            reuse_existing=True,
            commit=commit,
        )
        profile.next_run_at = None
        if commit:
            self.session.commit()
            self.session.refresh(profile)
        else:
            self.session.flush()
        return profile

    def profile_options(self) -> list[dict[str, str]]:
        slugs = [spec.niche_slug for spec in PROFILE_TRADE_CATALOG.values()]
        stored = {
            niche.slug: niche
            for niche in self.session.scalars(
                select(NicheModel).where(NicheModel.slug.in_(slugs))
            )
        }
        return [
            {"key": spec.key, "label": spec.label}
            for spec in PROFILE_TRADE_CATALOG.values()
            if spec.niche_slug not in stored or stored[spec.niche_slug].active
        ]

    def list(self):
        return [self._read(model) for model in self.territories.list()]

    def get(self, territory_id: str):
        return self.territories.get(territory_id)

    def get_read(self, territory_id: str) -> TerritoryRead:
        return self._read(self.territories.get(territory_id))

    def update(self, territory_id: str, update: TerritoryUpdate):
        model = self.territories.get(territory_id)
        values = update.model_dump(mode="python", exclude_unset=True)
        if "city" in values:
            values["city"] = normalize_text(values["city"])
            values["market_key"] = semantic_key(values["city"]) or model.market_key
            center = market_center(values["city"])
            if model.trade_keys and center is None:
                raise ValidationError(
                    "market coordinates are unavailable",
                    {
                        "city": values["city"],
                        "reason": "A profile radius requires a stored market center.",
                    },
                )
            if center is not None:
                values["latitude"], values["longitude"] = center
        if "signal_keys" in values:
            values["signal_keys"] = (
                _clean_profile_keys(values["signal_keys"])
                if model.trade_keys
                else _clean_keys(values["signal_keys"])
            )
        if "exclusion_keys" in values:
            values["exclusion_keys"] = (
                _clean_profile_keys(values["exclusion_keys"])
                if model.trade_keys
                else _clean_keys(values["exclusion_keys"])
            )
        if "trade_keys" in values:
            values["trade_keys"] = list(
                dict.fromkeys(
                    value.value if hasattr(value, "value") else str(value)
                    for value in values["trade_keys"]
                )
            )
        if "customer_kind" in values and hasattr(values["customer_kind"], "value"):
            values["customer_kind"] = values["customer_kind"].value
        criteria_fields = {
            "city",
            "radius_km",
            "trade_keys",
            "customer_kind",
            "signal_keys",
            "exclusion_keys",
            "batch_size",
            "min_fit",
        }
        criteria_changed = bool(criteria_fields & values.keys())
        normalized = TerritoryUpdate.model_validate(
            {key: value for key, value in values.items() if key != "market_key"}
        )
        model = self.territories.update(territory_id, normalized, commit=False)
        if "market_key" in values:
            model.market_key = values["market_key"]
        if criteria_changed:
            model.criteria_version += 1
            criteria = {
                "city": model.city,
                "radius_km": model.radius_km,
                "trade_keys": model.trade_keys,
                "customer_kind": model.customer_kind,
                "signal_keys": model.signal_keys,
                "exclusion_keys": model.exclusion_keys,
                "batch_size": model.batch_size,
                "min_fit": model.min_fit,
            }
            if not model.trade_keys:
                criteria["niche_id"] = model.niche_id
            model.criteria_hash = _criteria_hash(criteria)
        if "refill_policy" in values:
            policy = (
                values["refill_policy"].value
                if hasattr(values["refill_policy"], "value")
                else str(values["refill_policy"])
            )
            interval_days = {"weekly": 7, "biweekly": 14, "monthly": 30}.get(policy)
            model.next_run_at = (
                utcnow() + timedelta(days=interval_days)
                if interval_days is not None
                else None
            )
        self.session.commit()
        self.session.refresh(model)
        return model

    def delete(self, territory_id: str) -> None:
        self.territories.delete(territory_id)

    def list_deliveries(self, territory_id: str):
        return self.territories.list_deliveries(territory_id)

    def _read(self, model) -> TerritoryRead:
        deliveries = self.territories.list_deliveries(model.id)
        outcomes = list(
            self.session.scalars(
                select(LeadOutcomeModel).where(
                    LeadOutcomeModel.workspace_id == self.workspace_id,
                    LeadOutcomeModel.territory_id == model.id,
                )
            )
        )
        contacted = {
            outcome.lead_id
            for outcome in outcomes
            if outcome.outcome == LeadOutcome.CONTACTED.value
        }
        positive = {
            outcome.lead_id
            for outcome in outcomes
            if LeadOutcome(outcome.outcome) in POSITIVE_OUTCOMES
        }
        return TerritoryRead.model_validate(model).model_copy(
            update={
                "last_delivery_count": deliveries[0].new_contact_count if deliveries else 0,
                "unviewed_delivery_count": sum(
                    delivery.viewed_at is None and delivery.status in {"ready", "partial"}
                    for delivery in deliveries
                ),
                "positive_outcome_rate": (
                    round(len(contacted & positive) / len(contacted), 4)
                    if contacted
                    else 0.0
                ),
            }
        )

    def _ensure_profile_niche(self, trade_key: str, *, city: str) -> NicheModel:
        spec = profile_trade_spec(trade_key)
        niche = self.session.scalar(
            select(NicheModel).where(NicheModel.slug == spec.niche_slug).limit(1)
        )
        if niche is not None:
            if not niche.active:
                raise ValidationError(
                    "selected business type is not available",
                    {"trade": trade_key},
                )
            return niche
        niche = NicheModel(
            id=new_id("niche"),
            slug=spec.niche_slug,
            label=spec.niche_label,
            category=spec.niche_category,
            default_query=f"{spec.niche_label} in {city}",
            active=True,
        )
        self.session.add(niche)
        self.session.flush()
        return niche

    def _confirmed_niche(self, data: TerritoryCreate) -> NicheModel:
        if data.niche_id:
            niche = self.session.scalar(
                select(NicheModel).where(
                    NicheModel.id == data.niche_id,
                    NicheModel.active.is_(True),
                )
            )
            if niche is None:
                raise NotFoundError("niche not found", {"niche_id": data.niche_id})
            return niche
        existing = self.session.scalar(
            select(NicheModel).where(NicheModel.slug == _slug(data.niche_slug)).limit(1)
        )
        if existing is not None:
            return existing
        niche = NicheModel(
            id=new_id("niche"),
            slug=_slug(data.niche_slug),
            label=normalize_text(data.niche_label),
            category=normalize_text(data.niche_category or data.niche_label),
            default_query=f"{data.niche_label} in {data.market_key}",
            active=True,
        )
        self.session.add(niche)
        self.session.flush()
        return niche


def parse_territory_request(value: str, *, default_market: str) -> tuple[str, str]:
    normalized = normalize_text(value)
    match = re.match(r"^(?P<category>.+?)\s+in\s+(?P<market>.+)$", normalized, flags=re.I)
    if match:
        category = normalize_text(match.group("category"))
        market = normalize_text(match.group("market"))
        if category and market:
            return category, market
    return normalized, normalize_text(default_market) or "unknown"


def _slug(value: str) -> str:
    slug = (semantic_key(value) or "local_business").replace(" ", "_")
    return slug[:255]


def _title_label(value: str) -> str:
    return " ".join(
        word.upper() if word.lower() in {"hvac", "b2b"} else word.title()
        for word in value.split()
    )


def _criteria_hash(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _structured_profile_criteria(data: TerritoryCreate) -> dict:
    return {
        "trades": list(data.trade_keys),
        "customer_kind": data.customer_kind.value,
        "city": semantic_key(data.city or data.market_key),
        "radius_km": data.radius_km,
        "signals": list(data.signal_keys),
        "exclude": list(data.exclusion_keys),
        "limit": data.batch_size,
        "exclude_already_delivered": True,
    }


def _clean_keys(values: list[str]) -> list[str]:
    return list(dict.fromkeys(semantic_key(value) for value in values if semantic_key(value)))


def _clean_profile_keys(values: list[str]) -> list[str]:
    return list(
        dict.fromkeys(
            key.replace(" ", "_")
            for value in values
            if (key := semantic_key(value))
        )
    )
