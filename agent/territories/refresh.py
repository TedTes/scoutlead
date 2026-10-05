from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from campaigns.schemas import CampaignCreate, CampaignGoalType
from campaigns.service import CampaignService
from db.models import (
    LeadModel,
    NicheModel,
    ProfileDeliveryItemModel,
    TerritoryDeliveryModel,
)
from evaluation.digital_opportunity import (
    has_minimum_opportunity,
    opportunity_score_from_sources,
)
from leads.schemas import AgentFitStatus, LeadRead
from shared.errors import ConflictError
from shared.utils import new_id, utcnow
from territories.matching import ProfileMatchService
from territories.profile_catalog import profile_trade_spec
from territories.repository import TerritoryRepository
from territories.schemas import TerritoryMinFit


class TerritoryRefreshService:
    def __init__(
        self,
        *,
        session: Session,
        campaigns: CampaignService,
        workspace_id: str,
    ) -> None:
        self.session = session
        self.campaigns = campaigns
        self.territories = TerritoryRepository(session, workspace_id=workspace_id)
        self.workspace_id = workspace_id

    def refresh(
        self,
        territory_id: str,
        *,
        scheduled_for: datetime | None = None,
    ) -> TerritoryDeliveryModel:
        territory = self.territories.get(territory_id)
        if territory.status != "active":
            raise ConflictError("paused territories cannot be refreshed")
        scheduled_for = _schedule_time(scheduled_for or utcnow())
        existing = self.territories.delivery_for_schedule(territory.id, scheduled_for)
        if existing and existing.status != "failed":
            return existing
        niches = _territory_niches(self.session, territory)
        if not niches:
            raise ConflictError(
                "profile trades do not resolve to active niches",
                {"profile_id": territory.id, "trade_keys": territory.trade_keys},
            )
        niche_ids = [item.id for item in niches]
        campaign = self.campaigns.create_profile_delivery(
            CampaignCreate(
                product_id=territory.product_id,
                territory_id=territory.id,
                name=f"{territory.label} · {scheduled_for.date().isoformat()}",
                goal_type=CampaignGoalType.SELL,
                source_inputs={
                    "profile_match": {
                        "version": 1,
                        "product_id": territory.product_id,
                        "profile_id": territory.id,
                        "niche_ids": niche_ids,
                        "trades": list(territory.trade_keys or []),
                        "customer_kind": territory.customer_kind,
                        "market": {
                            "city": territory.city,
                            "radius_km": territory.radius_km,
                        },
                        "signals": list(territory.signal_keys or []),
                        "exclude": list(territory.exclusion_keys or []),
                        "limit": territory.batch_size,
                        "exclude_already_delivered": True,
                    },
                },
                max_leads=territory.batch_size,
                channels=["email"],
            )
        )
        if existing:
            delivery = existing
            delivery.campaign_id = campaign.id
            delivery.started_at = utcnow()
            delivery.status = "running"
            delivery.failure_reason = None
        else:
            delivery = TerritoryDeliveryModel(
                id=new_id("delivery"),
                workspace_id=self.workspace_id,
                territory_id=territory.id,
                campaign_id=campaign.id,
                scheduled_for=scheduled_for,
                started_at=utcnow(),
                status="running",
                new_contact_count=0,
            )
            self.session.add(delivery)
        self.session.commit()
        try:
            rows = ProfileMatchService(self.session).match(
                profile=territory,
                niche_ids=niche_ids,
                limit=territory.batch_size,
            )
            self.campaigns.materialize_profile_matches(campaign.id, rows)
            contacts = self.contacts(delivery, min_fit=TerritoryMinFit(territory.min_fit))
            delivered_at = utcnow()
            for contact in contacts:
                if not contact.business_id:
                    continue
                self.session.add(
                    ProfileDeliveryItemModel(
                        id=new_id("profile_delivery_item"),
                        profile_id=territory.id,
                        delivery_id=delivery.id,
                        business_id=contact.business_id,
                        delivered_at=delivered_at,
                    )
                )
            delivery.new_contact_count = len(contacts)
            delivery.status = "ready" if contacts else "empty"
            delivery.delivered_at = delivered_at
            territory.last_run_at = delivery.delivered_at
            territory.next_run_at = _next_run_at(
                scheduled_for,
                refill_policy=territory.refill_policy,
            )
            territory.updated_at = utcnow()
            self.session.commit()
            self.session.refresh(delivery)
            return delivery
        except Exception as exc:
            delivery.status = "failed"
            delivery.failure_reason = str(exc)[:2000]
            territory.next_run_at = utcnow() + timedelta(hours=1)
            self.session.commit()
            raise

    def contacts(
        self,
        delivery: TerritoryDeliveryModel,
        *,
        min_fit: TerritoryMinFit,
    ) -> list[LeadRead]:
        leads = list(
            self.session.scalars(
                select(LeadModel)
                .where(LeadModel.campaign_id == delivery.campaign_id)
            )
        )
        return eligible_delivery_leads(leads, min_fit=min_fit)


def eligible_delivery_leads(
    leads: list[LeadModel],
    *,
    min_fit: TerritoryMinFit,
) -> list[LeadRead]:
    allowed = {AgentFitStatus.GOOD_FIT.value}
    if min_fit == TerritoryMinFit.MAYBE:
        allowed.add(AgentFitStatus.MAYBE.value)
    eligible = []
    for lead_model in leads:
        if not isinstance(lead_model.qualification, dict):
            continue
        if lead_model.qualification.get("fit_status") not in allowed:
            continue
        lead = LeadRead.model_validate(lead_model)
        if not _is_business_index_match(lead) and not has_minimum_opportunity(
            lead.raw_sources,
            minimum="moderate",
        ):
            continue
        eligible.append(lead)
    return sorted(
        eligible,
        key=_delivery_sort_key,
        reverse=True,
    )


def _delivery_sort_key(lead: LeadRead) -> tuple[float, float, float, float]:
    profile_match = _profile_match(lead)
    if profile_match is not None:
        rank_position = float(profile_match.get("rank_position") or 1_000_000)
        distance = profile_match.get("distance_km")
        return (
            2.0,
            float(profile_match.get("score") or 0),
            -float(distance) if isinstance(distance, (int, float)) else float("-inf"),
            -rank_position,
        )
    return (
        1.0,
        float(opportunity_score_from_sources(lead.raw_sources)),
        lead.rank_score
        if lead.rank_score is not None
        else float(lead.qualification.score if lead.qualification else 0),
        lead.created_at.timestamp(),
    )


def _profile_match(lead: LeadRead) -> dict | None:
    stack: list[object] = list(lead.raw_sources)
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            profile_match = value.get("profile_match")
            if isinstance(profile_match, dict) and profile_match.get("status") == "matched":
                return profile_match
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
    return None


def _schedule_time(value: datetime) -> datetime:
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).replace(microsecond=0)


def _next_run_at(value: datetime, *, refill_policy: str) -> datetime | None:
    days = {
        "weekly": 7,
        "biweekly": 14,
        "monthly": 30,
    }.get(refill_policy)
    return value + timedelta(days=days) if days else None


def _territory_niches(session: Session, territory) -> list[NicheModel]:
    keys = list(territory.trade_keys or [])
    if keys:
        slugs = [profile_trade_spec(key).niche_slug for key in keys]
        niches = list(
            session.scalars(select(NicheModel).where(NicheModel.slug.in_(slugs)))
        )
        by_slug = {niche.slug: niche for niche in niches if niche.active}
        return [by_slug[slug] for slug in slugs if slug in by_slug]

    primary = session.get(NicheModel, territory.niche_id)
    return [primary] if primary is not None and primary.active else []


def _is_business_index_match(lead: LeadRead) -> bool:
    stack: list[object] = list(lead.raw_sources)
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            if (
                value.get("match_origin") == "profile_sql"
                and isinstance(value.get("profile_match"), dict)
                and value["profile_match"].get("status") == "matched"
            ):
                return True
            if value.get("match_origin") == "business_index" and value.get("business_facts"):
                return True
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
    return False
