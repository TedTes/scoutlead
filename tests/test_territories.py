from datetime import datetime, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
import pytest

from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignCreate, LeadSeedInput
from db.models import NicheModel, QueueJobModel, TerritoryModel
from db.session import create_database
from products.repository import ProductRepository
from products.schemas import ProductCreate, QualificationCriterion
from shared.errors import ConflictError, NotFoundError, ValidationError
from shared.utils import new_id
from territories.schemas import TerritoryCreate, TerritoryResolveRequest
from territories.service import TerritoryService
from territories.dedupe import exclude_previously_delivered_rows
from territories.refresh import TerritoryRefreshService
from territories.scheduler import enqueue_due_territories
from leads.repository import LeadRepository
from leads.schemas import AgentFitStatus, QualificationResult
from outcomes.schemas import LeadOutcome, LeadOutcomeCreate, OutcomeChannel
from outcomes.service import OutcomeService
from territories.metrics import TerritoryMetricsService


def test_resolve_existing_niche_is_read_only() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        niche = _niche(session, slug="home_service_hvac", label="HVAC contractors")
        service = TerritoryService(session, workspace_id="workspace:first")

        resolution = service.resolve(
            TerritoryResolveRequest(
                product_id=offer.id,
                request="HVAC contractors in Toronto",
            )
        )

        assert resolution.existing_niche is True
        assert resolution.niche_id == niche.id
        assert resolution.market_key == "toronto"
        assert session.scalar(select(func.count()).select_from(TerritoryModel)) == 0


def test_resolve_unknown_niche_proposes_without_creating_it() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        service = TerritoryService(session, workspace_id="workspace:first")

        resolution = service.resolve(
            TerritoryResolveRequest(
                product_id=offer.id,
                request="mobile bicycle mechanics in Hamilton",
            )
        )

        assert resolution.existing_niche is False
        assert resolution.niche_slug == "mobile_bicycle_mechanics"
        assert resolution.market_key == "hamilton"
        assert session.scalar(select(func.count()).select_from(NicheModel)) == 0


def test_confirmed_territory_creation_can_create_a_new_niche() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        service = TerritoryService(session, workspace_id="workspace:first")
        data = TerritoryCreate(
            product_id=offer.id,
            niche_slug="mobile_bicycle_mechanics",
            niche_label="Mobile bicycle mechanics",
            niche_category="bicycle repair",
            market_key="Hamilton",
            confirmed=True,
        )

        territory = service.create(data)

        assert territory.market_key == "hamilton"
        assert territory.workspace_id == "workspace:first"
        assert territory.niche.slug == "mobile_bicycle_mechanics"


def test_territory_creation_requires_confirmation_and_rejects_duplicates() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        niche = _niche(session, slug="home_service_hvac", label="HVAC contractors")
        service = TerritoryService(session, workspace_id="workspace:first")
        data = TerritoryCreate(
            product_id=offer.id,
            niche_id=niche.id,
            niche_slug=niche.slug,
            niche_label=niche.label,
            market_key="Toronto",
        )

        with pytest.raises(ValidationError):
            service.create(data)

        confirmed = data.model_copy(update={"confirmed": True})
        service.create(confirmed)
        with pytest.raises(ConflictError):
            service.create(confirmed)


def test_territories_are_scoped_by_workspace() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        niche = _niche(session, slug="home_service_hvac", label="HVAC contractors")
        territory = TerritoryService(session, workspace_id="workspace:first").create(
            TerritoryCreate(
                product_id=offer.id,
                niche_id=niche.id,
                niche_slug=niche.slug,
                niche_label=niche.label,
                market_key="Toronto",
                confirmed=True,
            )
        )

        assert [item.id for item in TerritoryService(session, workspace_id="workspace:first").list()] == [
            territory.id
        ]
        with pytest.raises(NotFoundError):
            TerritoryService(session, workspace_id="workspace:second").get(territory.id)


def test_refresh_is_idempotent_and_delivery_contains_only_allowed_fit() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        niche = _niche(session, slug="home_service_hvac", label="HVAC contractors")
        territory = TerritoryService(session, workspace_id="workspace:first").create(
            TerritoryCreate(
                product_id=offer.id,
                niche_id=niche.id,
                niche_slug=niche.slug,
                niche_label=niche.label,
                market_key="Toronto",
                batch_size=2,
                confirmed=True,
            )
        )
        campaigns = _FakeCampaigns(session, workspace_id="workspace:first")
        refresh = TerritoryRefreshService(
            session=session,
            campaigns=campaigns,
            workspace_id="workspace:first",
        )
        scheduled = datetime(2026, 9, 28, tzinfo=timezone.utc)

        first = refresh.refresh(territory.id, scheduled_for=scheduled)
        second = refresh.refresh(territory.id, scheduled_for=scheduled)

        assert first.id == second.id
        assert first.status == "ready"
        assert first.new_contact_count == 2
        assert campaigns.run_count == 1
        assert all(
            lead.territory_id == territory.id
            for lead in refresh.contacts(first, min_fit=territory.min_fit)
        )


def test_failed_refresh_reuses_delivery_on_retry() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        niche = _niche(session, slug="home_service_hvac", label="HVAC contractors")
        territory = TerritoryService(session, workspace_id="workspace:first").create(
            TerritoryCreate(
                product_id=offer.id,
                niche_id=niche.id,
                niche_slug=niche.slug,
                niche_label=niche.label,
                market_key="Toronto",
                confirmed=True,
            )
        )
        campaigns = _FakeCampaigns(
            session,
            workspace_id="workspace:first",
            fail_first=True,
        )
        refresh = TerritoryRefreshService(
            session=session,
            campaigns=campaigns,
            workspace_id="workspace:first",
        )
        scheduled = datetime(2026, 9, 28, tzinfo=timezone.utc)

        with pytest.raises(RuntimeError):
            refresh.refresh(territory.id, scheduled_for=scheduled)
        failed = refresh.territories.list_deliveries(territory.id)[0]
        assert failed.status == "failed"

        retried = refresh.refresh(territory.id, scheduled_for=scheduled)
        assert retried.id == failed.id
        assert retried.status == "ready"
        assert campaigns.run_count == 2


def test_scheduler_enqueues_one_active_job_per_territory_and_date() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        niche = _niche(session, slug="home_service_hvac", label="HVAC contractors")
        territory = TerritoryService(session, workspace_id="workspace:first").create(
            TerritoryCreate(
                product_id=offer.id,
                niche_id=niche.id,
                niche_slug=niche.slug,
                niche_label=niche.label,
                market_key="Toronto",
                confirmed=True,
            )
        )
        territory.next_run_at = datetime(2026, 9, 28, tzinfo=timezone.utc)
        session.commit()
        now = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)

        enqueue_due_territories(session, now=now)
        enqueue_due_territories(session, now=now)

        jobs = list(session.scalars(select(QueueJobModel)))
        assert len(jobs) == 1
        assert jobs[0].payload["territory_id"] == territory.id


def test_previous_territory_business_is_excluded_from_future_rows() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        niche = _niche(session, slug="home_service_hvac", label="HVAC contractors")
        territory = TerritoryService(session, workspace_id="workspace:first").create(
            TerritoryCreate(
                product_id=offer.id,
                niche_id=niche.id,
                niche_slug=niche.slug,
                niche_label=niche.label,
                market_key="Toronto",
                confirmed=True,
            )
        )
        repo = CampaignRepository(session, workspace_id="workspace:first")
        first_campaign = repo.create(
            CampaignCreate(
                product_id=offer.id,
                territory_id=territory.id,
                name="First",
                max_leads=2,
            )
        )
        lead = LeadRepository(session, workspace_id="workspace:first").create_from_seed(
            first_campaign.id,
            offer.id,
            LeadSeedInput(
                company_name="Delivered HVAC",
                website_url="https://delivered.example",
                geography="Toronto",
            ),
        )
        next_campaign = repo.create(
            CampaignCreate(
                product_id=offer.id,
                territory_id=territory.id,
                name="Second",
                max_leads=2,
            )
        )

        rows = exclude_previously_delivered_rows(
            session,
            campaign_id=next_campaign.id,
            product_id=offer.id,
            rows=[
                {"raw": {"canonical_business_id": lead.business_id}, "title": "Delivered"},
                {"raw": {"canonical_business_id": "business:new"}, "title": "New"},
            ],
        )
        assert [row["title"] for row in rows] == ["New"]


def test_territory_metrics_report_coverage_and_conversion() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        niche = _niche(session, slug="home_service_hvac", label="HVAC contractors")
        territory = TerritoryService(session, workspace_id="workspace:first").create(
            TerritoryCreate(
                product_id=offer.id,
                niche_id=niche.id,
                niche_slug=niche.slug,
                niche_label=niche.label,
                market_key="Toronto",
                batch_size=2,
                confirmed=True,
            )
        )
        refresh = TerritoryRefreshService(
            session=session,
            campaigns=_FakeCampaigns(session, workspace_id="workspace:first"),
            workspace_id="workspace:first",
        )
        delivery = refresh.refresh(territory.id)
        leads = refresh.contacts(delivery, min_fit=territory.min_fit)
        outcomes = OutcomeService(session, workspace_id="workspace:first")
        outcomes.record(
            leads[0].id,
            LeadOutcomeCreate(
                outcome=LeadOutcome.CONTACTED,
                channel=OutcomeChannel.EMAIL,
            ),
        )
        outcomes.record(
            leads[0].id,
            LeadOutcomeCreate(
                outcome=LeadOutcome.REPLIED_POSITIVE,
                channel=OutcomeChannel.EMAIL,
            ),
        )
        outcomes.record(
            leads[0].id,
            LeadOutcomeCreate(
                outcome=LeadOutcome.MEETING_BOOKED,
                channel=OutcomeChannel.EMAIL,
            ),
        )

        metrics = TerritoryMetricsService(
            session,
            workspace_id="workspace:first",
        ).calculate(territory.id, weeks=1)
        assert metrics.totals.delivered == 2
        assert metrics.totals.contacted == 1
        assert metrics.totals.meetings == 1
        assert metrics.totals.positive_reply_rate == 1.0
        assert metrics.totals.outcome_coverage == 0.5


def _session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _offer(session, *, workspace_id: str):
    return ProductRepository(session, workspace_id=workspace_id).create(
        ProductCreate(
            product_name="Contractor Coverage",
            offer_summary="Commercial insurance for independent contractors.",
            target_customer="Independent home-service contractors",
            target_geography="Greater Toronto Area",
            qualification_criteria=[
                QualificationCriterion(label="Operates a local service business", required=True)
            ],
            ideal_customer_signals=["service fleet"],
        )
    )


def _niche(session, *, slug: str, label: str) -> NicheModel:
    niche = NicheModel(
        id=new_id("niche"),
        slug=slug,
        label=label,
        category=label,
        default_query=label,
        active=True,
    )
    session.add(niche)
    session.commit()
    return niche


class _FakeCampaigns:
    def __init__(self, session, *, workspace_id: str, fail_first: bool = False) -> None:
        self.session = session
        self.repository = CampaignRepository(session, workspace_id=workspace_id)
        self.leads = LeadRepository(session, workspace_id=workspace_id)
        self.fail_first = fail_first
        self.run_count = 0

    def create(self, campaign):
        return self.repository.create(campaign)

    def run_contact_listing(self, campaign_id: str):
        self.run_count += 1
        if self.fail_first and self.run_count == 1:
            raise RuntimeError("temporary source failure")
        campaign = self.repository.get(campaign_id)
        for index, fit_status in enumerate(
            (AgentFitStatus.GOOD_FIT, AgentFitStatus.MAYBE),
            start=1,
        ):
            lead = self.leads.create_from_seed(
                campaign.id,
                campaign.product_id,
                LeadSeedInput(
                    company_name=f"HVAC {self.run_count}-{index}",
                    website_url=f"https://hvac-{self.run_count}-{index}.example",
                    geography="Toronto",
                ),
            )
            self.leads.attach_qualification(
                lead.id,
                QualificationResult(
                    qualified=True,
                    fit_status=fit_status,
                    score=80,
                    rationale="Matches the niche.",
                    recommended_next_step="Review contact.",
                ),
            )
