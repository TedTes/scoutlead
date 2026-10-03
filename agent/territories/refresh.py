from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.llm import LLMClient
from business_index.schemas import BusinessIndexSearch, OpportunityType, SearchContract
from business_index.search import BusinessIndexSearchService
from campaigns.schemas import CampaignCreate, CampaignGoalType
from campaigns.service import CampaignService
from db.models import LeadModel, NicheModel, TerritoryDeliveryModel
from evaluation.digital_opportunity import (
    has_minimum_opportunity,
    opportunity_score_from_sources,
)
from leads.schemas import (
    AgentFitStatus,
    ContactPolicyStatus,
    ContactVerificationStatus,
    LeadRead,
)
from leads.approach_service import LeadApproachService
from products.repository import ProductRepository
from products.schemas import ProductRead
from search_evaluations.service import SearchEvaluationService
from shared.errors import ConflictError
from shared.logger import get_logger
from shared.utils import new_id, utcnow
from territories.repository import TerritoryRepository
from territories.dedupe import exclude_previously_delivered_rows
from territories.opportunity_audit import TerritoryOpportunityAuditor
from territories.schemas import TerritoryMinFit


logger = get_logger(__name__)


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
        niche = self.session.get(NicheModel, territory.niche_id)
        product = ProductRead.model_validate(
            ProductRepository(self.session, workspace_id=self.workspace_id).get(
                territory.product_id
            )
        )
        query = territory.search_prompt or (
            f"{niche.label if niche else territory.label} in {territory.market_key}"
        )
        opportunity_type, search_contract = _territory_contract(
            territory,
            product=product,
            query=query,
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
                    "niche_slug": niche.slug if niche else None,
                    "source_request_intent": {
                        "business_category": niche.category if niche else territory.label,
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
            index_request = BusinessIndexSearch(
                niche_id=territory.niche_id,
                market_key=territory.market_key,
                opportunity_type=opportunity_type,
                evidence_fresh_after=utcnow()
                - timedelta(days=territory.evidence_max_age_days),
                result_count=territory.batch_size * 3,
                contract=search_contract,
                contract_hash=_territory_contract_hash(territory),
            )
            index_search = BusinessIndexSearchService(self.session)
            rows, decisions = index_search.search_with_diagnostics(index_request)
            if search_contract.requires_semantic_evaluation and self.llm is not None:
                evaluator = SearchEvaluationService(session=self.session, llm=self.llm)
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
            rows = exclude_previously_delivered_rows(
                self.session,
                campaign_id=campaign.id,
                product_id=territory.product_id,
                rows=rows,
            )[: territory.batch_size]
            self.campaigns.materialize_existing_matches(campaign.id, rows)
            contacts = self.contacts(delivery, min_fit=TerritoryMinFit(territory.min_fit))
            self._generate_approaches(contacts)
            contacts = self.contacts(delivery, min_fit=TerritoryMinFit(territory.min_fit))
            delivery.new_contact_count = len(contacts)
            delivery.status = "ready" if contacts else "partial"
            delivery.delivered_at = utcnow()
            territory.last_run_at = delivery.delivered_at
            territory.next_run_at = scheduled_for + timedelta(days=7)
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
            if not _has_usable_contact(lead):
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

    def _generate_approaches(self, contacts: list[LeadRead]) -> None:
        if self.llm is None:
            return
        service = LeadApproachService(
            session=self.session,
            llm=self.llm,
            workspace_id=self.workspace_id,
        )
        for contact in contacts:
            try:
                service.generate(contact.id)
            except Exception as exc:
                # Approach copy is supplemental; a copy failure must not discard a qualified contact.
                logger.warning(
                    "territory_approach_generation_failed lead_id=%s error=%s",
                    contact.id,
                    exc,
                )
                continue


def _schedule_time(value: datetime) -> datetime:
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def _has_usable_contact(lead: LeadRead) -> bool:
    if lead.contact_policy_status != ContactPolicyStatus.ALLOWED:
        return False
    email_is_usable = bool(
        lead.contact_email
        and lead.verification_status != ContactVerificationStatus.INVALID
    )
    return email_is_usable or bool(
        _raw_value(lead.raw_sources, {"phone", "phones", "contact_phone", "telephone"})
    )


def _territory_contract(
    territory,
    *,
    product: ProductRead,
    query: str,
) -> tuple[OpportunityType, SearchContract]:
    stored = territory.search_contract or {}
    try:
        opportunity_type = OpportunityType(
            stored.get("opportunity_type") or OpportunityType.ANY.value
        )
    except ValueError:
        opportunity_type = OpportunityType.ANY
    contract = SearchContract.from_dict(stored.get("search_contract"))
    if (
        contract.all_of
        or contract.any_of
        or contract.requires_semantic_evaluation
        or contract.contact_requirements
    ):
        return opportunity_type, contract
    return opportunity_type, SearchContract()


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


def _raw_value(sources: list[dict], keys: set[str]) -> str | None:
    stack: list[object] = list(sources)
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            for key, item in value.items():
                if key.casefold() in keys:
                    if isinstance(item, str) and item.strip():
                        return item.strip()
                    if isinstance(item, list):
                        first = next(
                            (
                                entry.strip()
                                for entry in item
                                if isinstance(entry, str) and entry.strip()
                            ),
                            None,
                        )
                        if first:
                            return first
                stack.append(item)
        elif isinstance(value, list):
            stack.extend(value)
    return None
