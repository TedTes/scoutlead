from __future__ import annotations

import hashlib
import json
import re

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
from shared.utils import new_id, normalize_text
from territories.repository import TerritoryRepository
from territories.schemas import (
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

    def create(self, data: TerritoryCreate):
        if not data.confirmed:
            raise ValidationError("territory resolution must be confirmed before creation")
        niche = self._confirmed_niche(data)
        contract_payload = data.search_contract or {
            "opportunity_type": OpportunityType.ANY.value,
            "search_contract": SearchContract().as_dict(),
        }
        stored_contract_hash = str(contract_payload.get("contract_hash") or "").strip()
        normalized = data.model_copy(
            update={
                "niche_slug": niche.slug,
                "niche_label": niche.label,
                "market_key": semantic_key(data.market_key) or "unknown",
                "search_contract": contract_payload,
                "criteria_hash": stored_contract_hash or _criteria_hash(contract_payload),
            }
        )
        return self.territories.create(normalized, niche_id=niche.id)

    def list(self):
        return [self._read(model) for model in self.territories.list()]

    def get(self, territory_id: str):
        return self.territories.get(territory_id)

    def update(self, territory_id: str, update: TerritoryUpdate):
        return self.territories.update(territory_id, update)

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
