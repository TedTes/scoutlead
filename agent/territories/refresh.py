from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.llm import LLMClient
from campaigns.schemas import CampaignCreate, CampaignGoalType
from campaigns.service import CampaignService
from db.models import LeadModel, NicheModel, TerritoryDeliveryModel
from leads.schemas import AgentFitStatus, LeadRead
from leads.approach_service import LeadApproachService
from shared.errors import ConflictError
from shared.logger import get_logger
from shared.utils import new_id, utcnow
from territories.repository import TerritoryRepository
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
    ) -> None:
        self.session = session
        self.campaigns = campaigns
        self.territories = TerritoryRepository(session, workspace_id=workspace_id)
        self.workspace_id = workspace_id
        self.llm = llm

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
        query = f"{niche.label if niche else territory.label} in {territory.market_key}"
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
            self.campaigns.run_contact_listing(campaign.id)
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
        eligible = [
            LeadRead.model_validate(lead)
            for lead in leads
            if isinstance(lead.qualification, dict)
            and lead.qualification.get("fit_status") in allowed
        ]
        return sorted(
            eligible,
            key=lambda lead: (
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
