from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.llm import LLMClient
from business_index.schemas import (
    BusinessIndexSearch,
    FactOperator,
    FactPredicate,
    OpportunityType,
    SearchContract,
)
from business_index.search import BusinessIndexSearchService
from campaigns.schemas import CampaignCreate, CampaignGoalType
from campaigns.service import CampaignService
from db.models import LeadModel, NicheModel, TerritoryDeliveryModel
from evaluation.digital_opportunity import (
    has_minimum_opportunity,
    opportunity_score_from_sources,
)
from leads.schemas import AgentFitStatus, LeadRead
from search_evaluations.service import SearchEvaluationService
from shared.errors import ConflictError
from shared.utils import new_id, utcnow
from territories.dedupe import exclude_previously_delivered_rows
from territories.opportunity_audit import TerritoryOpportunityAuditor
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
        llm: LLMClient | None = None,
        opportunity_auditor: TerritoryOpportunityAuditor | None = None,
    ) -> None:
        self.session = session
        self.campaigns = campaigns
        self.territories = TerritoryRepository(session, workspace_id=workspace_id)
        self.workspace_id = workspace_id
        self.llm = llm
        self.opportunity_auditor = opportunity_auditor

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
        niche = niches[0] if niches else self.session.get(NicheModel, territory.niche_id)
        niche_label = ", ".join(item.label for item in niches) or territory.label
        query = territory.search_prompt or (
            f"{territory.customer_kind} {niche_label} in {territory.city}"
        )
        opportunity_type, search_contract = _territory_contract(
            territory,
        )
        campaign = self.campaigns.create(
            CampaignCreate(
                product_id=territory.product_id,
                territory_id=territory.id,
                name=f"{territory.label} · {scheduled_for.date().isoformat()}",
                goal_type=CampaignGoalType.SELL,
                source_preset_id="google-places-local-business",
                source_input=query,
                source_inputs={
                    "niche_id": territory.niche_id,
                    "niche_ids": [item.id for item in niches],
                    "trade_keys": list(territory.trade_keys or []),
                    "customer_kind": territory.customer_kind,
                    "niche_slug": niche.slug if niche else None,
                    "profile_request": {
                        "product_id": territory.product_id,
                        "profile_id": territory.id,
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
                    "source_request_intent": {
                        "business_category": niche_label,
                        "location": territory.market_key,
                        "search_query": query,
                        "niche_id": territory.niche_id,
                    },
                    "business_index_contract": {
                        "niche_id": territory.niche_id,
                        "market_key": territory.market_key,
                        "opportunity_type": opportunity_type.value,
                        "evidence_max_age_days": territory.evidence_max_age_days,
                        "result_count": territory.batch_size,
                        "search_contract": search_contract.as_dict(),
                    },
                    "search_contract_hash": _territory_contract_hash(territory),
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
            index_search = BusinessIndexSearchService(self.session)
            evaluator = (
                SearchEvaluationService(session=self.session, llm=self.llm)
                if search_contract.requires_semantic_evaluation and self.llm is not None
                else None
            )
            rows_by_niche: list[list[dict]] = []
            for target_niche in niches or ([niche] if niche else []):
                index_request = BusinessIndexSearch(
                    niche_id=target_niche.id,
                    market_key=territory.market_key,
                    opportunity_type=opportunity_type,
                    evidence_fresh_after=utcnow()
                    - timedelta(days=territory.evidence_max_age_days),
                    result_count=territory.batch_size * 3,
                    contract=search_contract,
                    contract_hash=_territory_contract_hash(territory),
                )
                rows, decisions = index_search.search_with_diagnostics(index_request)
                if evaluator is None:
                    rows_by_niche.append(rows)
                    continue
                for decision in decisions:
                    if decision["status"] != "pending":
                        continue
                    evaluator.evaluate(
                        business_id=str(decision["business_id"]),
                        contract_hash=index_request.contract_hash,
                        contract=search_contract,
                        evidence_fresh_after=index_request.evidence_fresh_after,
                    )
                rows = index_search.search(index_request)
                rows_by_niche.append(rows)
            rows = _merge_niche_rows(
                rows_by_niche,
                limit=territory.batch_size * 3,
            )
            rows = exclude_previously_delivered_rows(
                self.session,
                campaign_id=campaign.id,
                territory_id=territory.id,
                rows=rows,
            )[: territory.batch_size]
            self.campaigns.materialize_existing_matches(campaign.id, rows)
            contacts = self.contacts(delivery, min_fit=TerritoryMinFit(territory.min_fit))
            delivery.new_contact_count = len(contacts)
            delivery.status = "ready" if contacts else "partial"
            delivery.delivered_at = utcnow()
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
        key=lambda lead: (
            opportunity_score_from_sources(lead.raw_sources),
            lead.rank_score
            if lead.rank_score is not None
            else float(lead.qualification.score if lead.qualification else 0),
            lead.created_at.timestamp(),
        ),
        reverse=True,
    )

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
    slugs = [profile_trade_spec(key).niche_slug for key in keys]
    niches = list(
        session.scalars(select(NicheModel).where(NicheModel.slug.in_(slugs)))
    ) if slugs else []
    by_slug = {niche.slug: niche for niche in niches if niche.active}
    ordered = [by_slug[slug] for slug in slugs if slug in by_slug]
    primary = session.get(NicheModel, territory.niche_id)
    if primary is not None and primary.active and primary.id not in {item.id for item in ordered}:
        ordered.insert(0, primary)
    return ordered


def _merge_niche_rows(rows_by_niche: list[list[dict]], *, limit: int) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()
    depth = 0
    while len(merged) < limit and any(depth < len(rows) for rows in rows_by_niche):
        for rows in rows_by_niche:
            if depth >= len(rows):
                continue
            row = rows[depth]
            business_id = str(row.get("raw", {}).get("canonical_business_id") or "")
            key = business_id or f"{row.get('title')}|{row.get('url')}"
            if key in seen:
                continue
            seen.add(key)
            merged.append(row)
            if len(merged) >= limit:
                break
        depth += 1
    return merged


def _territory_contract(
    territory,
) -> tuple[OpportunityType, SearchContract]:
    stored = territory.search_contract or {}
    try:
        opportunity_type = OpportunityType(
            stored.get("opportunity_type") or OpportunityType.ANY.value
        )
    except ValueError:
        opportunity_type = OpportunityType.ANY
    contract = SearchContract.from_dict(stored.get("search_contract"))
    return opportunity_type, _profile_contract(territory, contract)


def _profile_contract(territory, contract: SearchContract) -> SearchContract:
    ranking = list(contract.ranking)
    all_of = list(contract.all_of)
    semantic_exclusions = list(contract.semantic_exclusions)
    for signal in territory.signal_keys or []:
        predicate = _signal_predicate(signal)
        if predicate is not None:
            ranking.append(predicate)
    for exclusion in territory.exclusion_keys or []:
        key = _normalized_key(exclusion)
        if key in {"closed", "closed business", "inactive business"}:
            all_of.append(
                FactPredicate(
                    "business_operational",
                    FactOperator.EQUALS,
                    True,
                )
            )
            continue
        description = {
            "chain": "Business is a chain or national brand",
            "chains": "Business is a chain or national brand",
            "franchise": "Business is a franchise",
            "franchises": "Business is a franchise",
            "directory": "Result is a directory rather than an operating business",
            "directories": "Result is a directory rather than an operating business",
            "marketing agency": "Business is a marketing or web agency",
            "marketing agencies": "Business is a marketing or web agency",
            "agencies": "Business is a marketing or web agency",
        }.get(key)
        if description:
            semantic_exclusions.append(description)
    return SearchContract(
        all_of=tuple(_unique_predicates(all_of)),
        any_of=contract.any_of,
        ranking=tuple(_unique_predicates(ranking)),
        semantic_all_of=contract.semantic_all_of,
        semantic_any_of=contract.semantic_any_of,
        semantic_exclusions=tuple(dict.fromkeys(semantic_exclusions)),
        contact_requirements=(),
        unsupported=contract.unsupported,
    )


def _signal_predicate(value: str) -> FactPredicate | None:
    key = _normalized_key(value)
    if key in {"website missing", "website unavailable", "missing or broken website"}:
        return FactPredicate(
            "website_status",
            FactOperator.IN,
            ("missing", "unavailable", "parked"),
        )
    if key in {"quote flow missing", "no quote flow", "missing quote form"}:
        return FactPredicate(
            "quote_or_booking_form_present",
            FactOperator.EQUALS,
            False,
        )
    if key in {"contact form missing", "no contact form"}:
        return FactPredicate(
            "contact_form_present",
            FactOperator.EQUALS,
            False,
        )
    if key in {"low review count", "few reviews", "reviews under 15"}:
        return FactPredicate(
            "google_review_count",
            FactOperator.LESS_THAN,
            15.0,
        )
    if key in {"low rating", "rating under 4 3"}:
        return FactPredicate(
            "google_rating",
            FactOperator.LESS_THAN,
            4.3,
        )
    return None


def _unique_predicates(values: list[FactPredicate]) -> list[FactPredicate]:
    unique: dict[tuple, FactPredicate] = {}
    for value in values:
        raw = value.value if isinstance(value.value, tuple) else (value.value,)
        unique[(value.key, value.operator.value, *raw)] = value
    return list(unique.values())


def _normalized_key(value: str) -> str:
    return " ".join(value.strip().lower().replace("_", " ").replace("-", " ").split())


def _territory_contract_hash(territory) -> str:
    stored = territory.search_contract or {}
    return str(stored.get("contract_hash") or territory.criteria_hash)


def _is_business_index_match(lead: LeadRead) -> bool:
    stack: list[object] = list(lead.raw_sources)
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            if value.get("match_origin") == "business_index" and value.get("business_facts"):
                return True
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
    return False
