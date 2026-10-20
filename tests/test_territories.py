from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
import pytest

from campaigns.repository import CampaignRepository
from audience_runs.service import AudienceRunService, _territory_niches
from audience_runs.outreach import AudienceOutreachService
from audience_runs.schemas import AudienceResultUpdate
from campaigns.service import CampaignService
from business_facts.repository import (
    BusinessFactKey,
    BusinessFactRepository,
    BusinessFactValue,
)
from business_index.schemas import SearchContract
from campaigns.schemas import CampaignCreate, CampaignUpdate, LeadSeedInput
from canonical.repository import CanonicalRepository
from db.models import (
    BusinessIndexSegmentModel,
    BusinessModel,
    BusinessNicheMembershipModel,
    AudienceResultModel,
    AudienceRunModel,
    CampaignModel,
    CoverageRequestModel,
    LeadModel,
    LeadOutcomeModel,
    NicheModel,
    OutcomeModel,
    QueueJobModel,
    SeedBatchModel,
    SignalDefinitionModel,
    ServiceDefinitionModel,
    ServiceSignalMappingModel,
    TerritoryModel,
    ValidationResultModel,
)
from db.session import create_database
from job_queue.service import QueueService
from products.repository import ProductRepository
from products.schemas import ProductCreate, QualificationCriterion
from shared.errors import ConflictError, NotFoundError, ValidationError
from shared.utils import new_id, utcnow
from territories.routes import (
    create_audience as create_profile_route,
    current_audience_batch as current_profile_batch,
)
from territories.schemas import (
    ProfileCreate,
    TerritoryCreate,
    TerritoryRefillPolicy,
    TerritoryResolveRequest,
    TerritoryUpdate,
)
from territories.service import TerritoryService
from territories.changes import ProfileChangeService
from territories.refill import enqueue_refill_if_depleted
from territories.scheduler import enqueue_due_territories
from territories.source_expansion import enqueue_profile_source_expansion
from leads.repository import LeadRepository
from leads.schemas import (
    AgentFitStatus,
    ContactPolicyStatus,
    LeadContactPolicyUpdate,
    SuppressionScope,
)
from outcomes.schemas import LeadOutcome, LeadOutcomeCreate, OutcomeChannel
from outcomes.service import OutcomeService
from territories.metrics import TerritoryMetricsService
from territories.matching import ProfileMatchService


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


def test_audience_can_be_renamed_and_archived_from_the_visible_list() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        niche = _niche(session, slug="home_service_hvac", label="HVAC contractors")
        service = TerritoryService(session, workspace_id="workspace:first")
        territory = service.create(
            TerritoryCreate(
                product_id=offer.id,
                niche_id=niche.id,
                niche_slug=niche.slug,
                niche_label=niche.label,
                market_key="Toronto",
                label="Toronto HVAC",
                confirmed=True,
            )
        )

        service.update(territory.id, TerritoryUpdate(label="Priority HVAC accounts"))
        assert service.get(territory.id).label == "Priority HVAC accounts"

        service.delete(territory.id)

        archived = service.get(territory.id)
        assert archived.status == "archived"
        assert archived.next_run_at is None
        assert service.list() == []


def test_recreating_archived_audience_restores_it() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        niche = _niche(session, slug="home_service_hvac", label="HVAC contractors")
        service = TerritoryService(session, workspace_id="workspace:first")
        create = TerritoryCreate(
            product_id=offer.id,
            niche_id=niche.id,
            niche_slug=niche.slug,
            niche_label=niche.label,
            market_key="Toronto",
            label="Toronto HVAC",
            confirmed=True,
        )
        first = service.create(create)
        service.delete(first.id)

        restored = service.create(create.model_copy(update={"label": "Restored HVAC"}))

        assert restored.id == first.id
        assert restored.status == "active"
        assert restored.label == "Restored HVAC"
        assert [item.id for item in service.list()] == [first.id]


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


def test_profile_creation_only_persists_configuration_and_queues_initial_batch() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")

        result = create_profile_route(
            ProfileCreate(
                product_id=offer.id,
                trades=["painters"],
                customer_kind="residential",
                market={"city": "Toronto", "radius_km": 25},
                signals=["website_unavailable"],
                exclude=["franchises"],
            ),
            session,
            SimpleNamespace(workspace_id="workspace:first"),
        )

        assert result.audience.product_id == offer.id
        assert result.audience.city == "Toronto"
        assert result.audience.trade_keys == ["painters"]
        assert result.audience.customer_kind.value == "residential"
        assert result.audience.signal_keys == ["website_unavailable"]
        assert result.audience.exclusion_keys == ["franchises"]
        assert result.audience.batch_size == 25
        assert result.audience.refill_policy.value == "when_depleted"
        assert result.audience.next_run_at is None
        assert result.audience.search_prompt is None
        assert result.audience.search_contract == {}
        assert result.job.status.value == "queued"
        run = session.get(AudienceRunModel, result.job.payload["audience_run_id"])
        assert run is not None
        assert run.audience_id == result.audience.id
        assert session.scalar(select(func.count()).select_from(CampaignModel)) == 0


def test_profile_creation_can_schedule_recurring_runs() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")

        profile = TerritoryService(
            session,
            workspace_id="workspace:first",
        ).create_profile(
            ProfileCreate(
                product_id=offer.id,
                trades=["painters"],
                customer_kind="residential",
                market={"city": "Toronto", "radius_km": 25},
                refill_policy="weekly",
            )
        )

        assert profile.refill_policy == "weekly"
        assert profile.next_run_at is not None
        scheduled = profile.next_run_at.replace(tzinfo=timezone.utc)
        assert timedelta(days=6, hours=23) < scheduled - utcnow()
        assert scheduled - utcnow() <= timedelta(days=7)


def test_recreating_active_profile_reuses_it_and_deduplicates_refresh() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        auth = SimpleNamespace(workspace_id="workspace:first")
        data = ProfileCreate(
            product_id=offer.id,
            trades=["painters"],
            customer_kind="residential",
            market={"city": "Toronto", "radius_km": 25},
            signals=["website_unavailable"],
            exclude=["franchises"],
        )

        first = create_profile_route(data, session, auth)
        repeated = create_profile_route(data, session, auth)

        assert repeated.audience.id == first.audience.id
        assert repeated.job.id == first.job.id
        assert session.scalar(select(func.count()).select_from(TerritoryModel)) == 1
        assert session.scalar(select(func.count()).select_from(QueueJobModel)) == 1

        queued = session.get(QueueJobModel, first.job.id)
        assert queued is not None
        queued.status = "completed"
        session.commit()

        refilled = create_profile_route(data, session, auth)

        assert refilled.audience.id == first.audience.id
        assert refilled.job.id != first.job.id
        assert session.scalar(select(func.count()).select_from(TerritoryModel)) == 1
        assert session.scalar(select(func.count()).select_from(QueueJobModel)) == 2


def test_profile_route_requires_a_service_or_explicit_signal() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        auth = SimpleNamespace(workspace_id="workspace:first")

        with pytest.raises(ValidationError, match="at least one service"):
            create_profile_route(
                ProfileCreate(
                    product_id=offer.id,
                    trades=["painters"],
                    customer_kind="residential",
                    market={"city": "Toronto", "radius_km": 25},
                ),
                session,
                auth,
            )


def test_profile_source_expansion_queues_each_trade_once() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        profile = TerritoryService(
            session,
            workspace_id="workspace:first",
        ).create_profile(
            ProfileCreate(
                product_id=offer.id,
                trades=["painters", "roofers"],
                customer_kind="residential",
                market={"city": "Toronto", "radius_km": 25},
                limit=25,
            )
        )

        first = enqueue_profile_source_expansion(
            session,
            profile,
            google_places_configured=False,
            search_configured=False,
            openstreetmap_enabled=True,
            apify_sources=[],
            source_recipes=[],
        )
        repeated = enqueue_profile_source_expansion(
            session,
            profile,
            google_places_configured=False,
            search_configured=False,
            openstreetmap_enabled=True,
            apify_sources=[],
            source_recipes=[],
        )

        segments = list(session.scalars(select(BusinessIndexSegmentModel)))
        jobs = list(
            session.scalars(
                select(QueueJobModel).where(
                    QueueJobModel.type == "business_index.refresh"
                )
            )
        )
        assert repeated == first
        assert len(first) == 2
        assert len(segments) == 2
        assert len(jobs) == 2
        assert all(segment.target_business_count == 100 for segment in segments)
        assert all(segment.demand_count == 1 for segment in segments)
        assert all(
            [task["provider_id"] for task in segment.source_plan] == ["openstreetmap"]
            for segment in segments
        )


def test_profile_batch_distinguishes_scoring_retrying_and_failed() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        auth = SimpleNamespace(workspace_id="workspace:first")
        result = create_profile_route(
            ProfileCreate(
                product_id=offer.id,
                trades=["painters"],
                customer_kind="residential",
                market={"city": "Toronto", "radius_km": 25},
                signals=["website_unavailable"],
            ),
            session,
            auth,
        )

        completed = current_profile_batch(result.audience.id, session, auth)
        assert completed.state.value == "empty"
        assert completed.failure_class is None

        job = session.get(QueueJobModel, result.job.id)
        assert job is not None
        assert job.status == "completed"

        initial_run = session.get(
            AudienceRunModel,
            result.job.payload["audience_run_id"],
        )
        assert initial_run is not None
        initial_run.state = "matching"
        initial_run.completed_at = None
        job.status = "completed"
        session.commit()

        repaired = current_profile_batch(result.audience.id, session, auth)
        assert repaired.state.value == "empty"
        assert initial_run.state == "partial"
        assert job.status == "completed"

        run = AudienceRunService(
            session,
            workspace_id="workspace:first",
        ).create(result.audience.id)
        job = QueueService(session).enqueue_audience_run(run.id)
        job.status = "running"
        job.attempts = 2
        job.locked_at = utcnow()
        job.last_error = "HTTP 429 rate_limit_exceeded"
        session.commit()
        retrying = current_profile_batch(result.audience.id, session, auth)
        assert retrying.state.value == "retrying"
        assert retrying.failure_class == "rate_limit"
        assert retrying.retry_at == job.run_after

        job.status = "failed"
        session.commit()
        failed = current_profile_batch(result.audience.id, session, auth)
        assert failed.state.value == "failed"
        assert failed.failure_class == "rate_limit"


def test_profile_contract_rejects_missing_or_unsupported_batch_fields() -> None:
    valid = {
        "product_id": "product_1",
        "trades": ["painters"],
        "customer_kind": "residential",
        "market": {"city": "Toronto", "radius_km": 25},
    }

    with pytest.raises(ValueError):
        ProfileCreate.model_validate({**valid, "trades": []})
    with pytest.raises(ValueError):
        ProfileCreate.model_validate({**valid, "trades": ["dentists"]})
    with pytest.raises(ValueError):
        ProfileCreate.model_validate(
            {**valid, "market": {"city": "Toronto", "radius_km": 100}}
        )
    with pytest.raises(ValueError):
        ProfileCreate.model_validate(
            {**valid, "market": {"city": "United States, Canada", "radius_km": 25}}
        )
    with pytest.raises(ValueError):
        ProfileCreate.model_validate({**valid, "limit": 10})


def test_profile_options_come_from_backend_capabilities_and_hide_disabled_niches() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        service = TerritoryService(session, workspace_id="workspace:first")
        initial = service.profile_options()

        assert [option["key"] for option in initial] == [
            "painters",
            "hvac",
            "roofers",
            "plumbers",
            "electricians",
            "cleaners",
            "landscapers",
            "pest_control",
            "garage_doors",
        ]

        disabled = _niche(
            session,
            slug="home_service_plumbing",
            label="Plumbing contractors",
        )
        disabled.active = False
        session.commit()

        assert "plumbers" not in {
            option["key"] for option in service.profile_options()
        }


def test_profile_service_options_include_disabled_draft_services() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        signal = SignalDefinitionModel(
            id=new_id("signal"),
            key="language_selector_present",
            label="Language selector present",
            value_type="boolean",
            category="localization",
            status="active",
            collector_key="website_dom",
            extractor_key="language_selector_present",
            freshness_days=30,
            opportunity_direction="false_is_opportunity",
            config={},
            version=1,
        )
        active = ServiceDefinitionModel(
            id=new_id("service"),
            key="website_modernization",
            label="Website modernization",
            status="active",
            sort_order=10,
            version=1,
        )
        active.signal_mappings.append(
            ServiceSignalMappingModel(
                id=new_id("service_signal"),
                signal_definition=signal,
                weight=1,
                sort_order=0,
            )
        )
        preparing = ServiceDefinitionModel(
            id=new_id("service"),
            key="multilingual_localization",
            label="Multilingual localization",
            status="draft",
            sort_order=20,
            version=1,
        )
        preparing.signal_mappings.append(
            ServiceSignalMappingModel(
                id=new_id("service_signal"),
                signal_definition=signal,
                weight=1,
                sort_order=0,
            )
        )
        planned = ServiceDefinitionModel(
            id=new_id("service"),
            key="social_media_management",
            label="Social media management",
            status="draft",
            sort_order=30,
            version=1,
        )
        session.add_all([active, preparing, planned])
        session.commit()

        options = TerritoryService(
            session, workspace_id="workspace:first"
        ).profile_service_options()

        assert [(option["key"], option["enabled"], len(option["signals"])) for option in options] == [
            ("website_modernization", True, 1),
            ("multilingual_localization", False, 1),
            ("social_media_management", False, 0),
        ]


def test_profile_persists_multiple_mapped_trades_and_default_policy() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        profile = TerritoryService(
            session, workspace_id="workspace:first"
        ).create_profile(
            ProfileCreate(
                product_id=offer.id,
                trades=["painters", "hvac"],
                customer_kind="commercial",
                market={"city": "Toronto", "radius_km": 50},
                limit=40,
            )
        )

        assert profile.trade_keys == ["painters", "hvac"]
        assert profile.customer_kind == "commercial"
        assert profile.radius_km == 50
        assert profile.batch_size == 40
        assert profile.refill_policy == "when_depleted"
        assert profile.label == "Painters + HVAC · Toronto"
        assert set(
            session.scalars(
                select(NicheModel.slug).where(
                    NicheModel.slug.in_(["home_service_painting", "home_service_hvac"])
                )
            )
        ) == {"home_service_painting", "home_service_hvac"}


def test_profile_criteria_edit_increments_version_and_rehashes() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        service = TerritoryService(session, workspace_id="workspace:first")
        profile = service.create_profile(
            ProfileCreate(
                product_id=offer.id,
                trades=["painters"],
                customer_kind="residential",
                market={"city": "Toronto", "radius_km": 25},
            )
        )
        previous_hash = profile.criteria_hash

        updated = service.update(
            profile.id,
            TerritoryUpdate(
                radius_km=40,
                signal_keys=["No quote flow", "No quote flow"],
            ),
        )

        assert updated.criteria_version == 2
        assert updated.criteria_hash != previous_hash
        assert updated.radius_km == 40
        assert updated.signal_keys == ["no_quote_flow"]

        scheduled = service.update(
            profile.id,
            TerritoryUpdate(refill_policy=TerritoryRefillPolicy.WEEKLY),
        )
        assert scheduled.next_run_at is not None
        manual = service.update(
            profile.id,
            TerritoryUpdate(refill_policy=TerritoryRefillPolicy.MANUAL),
        )
        assert manual.next_run_at is None


def test_territory_preserves_the_saved_semantic_search_contract() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        niche = _niche(session, slug="home_service_hvac", label="HVAC contractors")
        contract = SearchContract(
            semantic_all_of=("Owner-operated business",),
            semantic_exclusions=("National franchises",),
        )
        stored = {
            "opportunity_type": "any",
            "search_contract": contract.as_dict(),
            "contract_hash": "saved-contract-hash",
        }

        territory = TerritoryService(session, workspace_id="workspace:first").create(
            TerritoryCreate(
                product_id=offer.id,
                niche_id=niche.id,
                niche_slug=niche.slug,
                niche_label=niche.label,
                market_key="Toronto",
                request="Owner-operated HVAC contractors in Toronto, excluding franchises",
                search_contract=stored,
                confirmed=True,
            )
        )

        assert territory.search_contract == stored
        assert territory.criteria_hash == "saved-contract-hash"


def test_profile_trade_keys_are_authoritative_over_legacy_primary_niche() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        hvac = _niche(session, slug="home_service_hvac", label="HVAC contractors")
        painters = _niche(
            session,
            slug="home_service_painting",
            label="Painting contractors",
        )
        profile = TerritoryService(
            session, workspace_id="workspace:first"
        ).create_profile(
            ProfileCreate(
                product_id=offer.id,
                trades=["hvac"],
                customer_kind="residential",
                market={"city": "Toronto", "radius_km": 25},
            )
        )
        profile.niche_id = painters.id
        session.commit()

        assert [niche.id for niche in _territory_niches(session, profile)] == [hvac.id]


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




def test_when_depleted_profile_enqueues_one_replacement_batch() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        niche = _niche(session, slug="home_service_hvac", label="HVAC contractors")
        _seed_hvac_businesses(session)
        territory = TerritoryService(session, workspace_id="workspace:first").create(
            TerritoryCreate(
                product_id=offer.id,
                niche_id=niche.id,
                niche_slug=niche.slug,
                niche_label=niche.label,
                market_key="Toronto",
                batch_size=2,
                refill_policy=TerritoryRefillPolicy.WHEN_DEPLETED,
                confirmed=True,
            )
        )
        service = AudienceRunService(session, workspace_id="workspace:first")
        initial_run = service.create(territory.id)
        service.process(initial_run.id)
        first_result = session.scalar(
            select(AudienceResultModel)
            .where(AudienceResultModel.run_id == initial_run.id)
            .limit(1)
        )
        assert first_result is not None
        service.update_result(
            first_result.id,
            AudienceResultUpdate(review_status="not_fit"),
        )

        assert enqueue_refill_if_depleted(session, territory.id) is True

        jobs = list(session.scalars(select(QueueJobModel)))
        assert len(jobs) == 1
        replacement = session.get(AudienceRunModel, jobs[0].payload["audience_run_id"])
        assert replacement is not None
        assert replacement.audience_id == territory.id
        assert replacement.id != initial_run.id




def test_audience_run_returns_new_results_then_reuses_previous_results() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        _niche(session, slug="home_service_hvac", label="HVAC contractors")
        _seed_hvac_businesses(session)
        businesses = list(
            session.scalars(select(BusinessModel).order_by(BusinessModel.display_name))
        )
        facts = BusinessFactRepository(session)
        facts.upsert(
            businesses[0].id,
            BusinessFactValue(
                key=BusinessFactKey.GOOGLE_RATING,
                value=4.8,
                observed_at=utcnow(),
                source_observation_id=None,
            ),
        )
        facts.upsert(
            businesses[0].id,
            BusinessFactValue(
                key=BusinessFactKey.GOOGLE_REVIEW_COUNT,
                value=37,
                observed_at=utcnow(),
                source_observation_id=None,
            ),
            commit=True,
        )
        profile = TerritoryService(
            session,
            workspace_id="workspace:first",
        ).create_profile(
            ProfileCreate(
                product_id=offer.id,
                trades=["hvac"],
                customer_kind="residential",
                market={"city": "Toronto", "radius_km": 25},
                signals=[],
                exclude=[],
                limit=15,
            )
        )
        profile.batch_size = 2
        session.commit()
        service = AudienceRunService(session, workspace_id="workspace:first")

        first = service.create(profile.id)
        first, first_needs_expansion = service.process(first.id)
        first_read = service.get_read(first.id)

        assert first.state == "ready"
        assert first_needs_expansion is False
        assert first.new_result_count == 2
        assert all(result.is_new for result in first_read.results)
        leads = service.latest_leads_for_audience(profile.id)
        assert {lead.contact_phone for lead in leads} == {
            "4165550101",
            "4165550102",
        }
        assert {(lead.google_rating, lead.google_review_count) for lead in leads} == {
            (4.8, 37),
            (None, None),
        }

        second = service.create(profile.id)
        visible_during_refill = service.latest_leads_for_audience(profile.id)

        assert [lead.business_id for lead in visible_during_refill] == [
            result.business_id for result in first_read.results
        ]

        second, second_needs_expansion = service.process(second.id)
        second_read = service.get_read(second.id)

        assert second.state == "ready"
        assert second_needs_expansion is False
        assert second.new_result_count == 0
        assert [result.business_id for result in second_read.results] == [
            result.business_id for result in first_read.results
        ]
        assert all(not result.is_new for result in second_read.results)


def test_audience_run_returns_partial_results_without_waiting_for_expansion() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        _niche(session, slug="home_service_hvac", label="HVAC contractors")
        _seed_hvac_businesses(session)
        profile = TerritoryService(
            session,
            workspace_id="workspace:first",
        ).create_profile(
            ProfileCreate(
                product_id=offer.id,
                trades=["hvac"],
                customer_kind="residential",
                market={"city": "Toronto", "radius_km": 25},
                signals=[],
                exclude=[],
                limit=25,
            )
        )
        service = AudienceRunService(session, workspace_id="workspace:first")

        run = service.create(profile.id)
        run, needs_expansion = service.process(run.id)

        assert run.state == "partial"
        assert run.result_count == 2
        assert run.completed_at is not None
        assert needs_expansion is False
        assert len(service.latest_leads_for_audience(profile.id)) == 2
        assert session.scalar(select(func.count()).select_from(CoverageRequestModel)) == 0


def test_audience_result_creates_outreach_records_only_after_user_action() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        _niche(session, slug="home_service_hvac", label="HVAC contractors")
        _seed_hvac_businesses(session)
        profile = TerritoryService(
            session,
            workspace_id="workspace:first",
        ).create_profile(
            ProfileCreate(
                product_id=offer.id,
                trades=["hvac"],
                customer_kind="residential",
                market={"city": "Toronto", "radius_km": 25},
                signals=[],
                exclude=[],
                limit=15,
            )
        )
        profile.batch_size = 1
        session.commit()
        runs = AudienceRunService(session, workspace_id="workspace:first")
        run = runs.create(profile.id)
        runs.process(run.id)
        result = runs.get_read(run.id).results[0]

        assert session.scalar(select(func.count()).select_from(CampaignModel)) == 0
        runs.update_result(
            result.id,
            AudienceResultUpdate(shortlisted=True),
        )
        outreach = AudienceOutreachService(
            session,
            workspace_id="workspace:first",
        )
        lead = outreach.promote(result.id)
        repeated = outreach.promote(result.id)
        OutcomeService(
            session,
            workspace_id="workspace:first",
        ).record(
            lead.id,
            LeadOutcomeCreate(
                outcome=LeadOutcome.CONTACTED,
                channel=OutcomeChannel.EMAIL,
            ),
        )

        assert lead.id == repeated.id
        assert lead.shortlisted_at is not None
        assert session.scalar(select(func.count()).select_from(CampaignModel)) == 1
        assert session.scalar(select(func.count()).select_from(LeadModel)) == 1
        batch = current_profile_batch(
            profile.id,
            session,
            SimpleNamespace(workspace_id="workspace:first"),
        )
        assert batch.outreach_campaign_id == lead.campaign_id
        assert batch.leads[0].outreach_lead_id == lead.id
        assert batch.leads[0].last_contacted_at is not None


def test_audience_result_suppression_blocks_shortlisting_without_creating_a_lead() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        _niche(session, slug="home_service_hvac", label="HVAC contractors")
        _seed_hvac_businesses(session)
        profile = TerritoryService(
            session,
            workspace_id="workspace:first",
        ).create_profile(
            ProfileCreate(
                product_id=offer.id,
                trades=["hvac"],
                customer_kind="residential",
                market={"city": "Toronto", "radius_km": 25},
                signals=[],
                exclude=[],
                limit=15,
            )
        )
        profile.batch_size = 1
        session.commit()
        runs = AudienceRunService(session, workspace_id="workspace:first")
        run = runs.create(profile.id)
        runs.process(run.id)
        result = runs.get_read(run.id).results[0]

        blocked = runs.update_contact_policy(
            result.id,
            LeadContactPolicyUpdate(
                status=ContactPolicyStatus.SUPPRESSED,
                reason="Do not contact.",
                scope=SuppressionScope.WORKSPACE,
            ),
        )

        assert blocked.contact_policy_status == ContactPolicyStatus.SUPPRESSED.value
        assert session.scalar(select(func.count()).select_from(LeadModel)) == 0
        with pytest.raises(ConflictError, match="blocked from outreach"):
            runs.update_result(result.id, AudienceResultUpdate(shortlisted=True))


def test_profile_match_excludes_only_explicit_true_classifications() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        _niche(session, slug="home_service_hvac", label="HVAC contractors")
        _seed_hvac_businesses(session)
        businesses = list(
            session.scalars(select(BusinessModel).order_by(BusinessModel.display_name))
        )
        businesses[0].is_chain = True
        businesses[1].is_chain = None
        session.commit()
        profile = TerritoryService(
            session,
            workspace_id="workspace:first",
        ).create_profile(
            ProfileCreate(
                product_id=offer.id,
                trades=["hvac"],
                customer_kind="residential",
                market={"city": "Toronto", "radius_km": 25},
                signals=[],
                exclude=["chains"],
                limit=25,
            )
        )

        rows = ProfileMatchService(session).match(
            profile=profile,
            niche_ids=[profile.niche_id],
            limit=25,
        )

        assert [row["title"] for row in rows] == [businesses[1].display_name]
        assert rows[0]["raw"]["profile_match"]["classifications"]["is_chain"] is None


def test_profile_match_ignores_quarantined_seed_membership() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        _niche(session, slug="home_service_hvac", label="HVAC contractors")
        _seed_hvac_businesses(session)
        memberships = list(
            session.scalars(
                select(BusinessNicheMembershipModel).order_by(
                    BusinessNicheMembershipModel.business_id
                )
            )
        )
        quarantined = SeedBatchModel(
            id="contaminated-v1",
            niche_id=memberships[0].niche_id,
            market_key="toronto",
            source="google_places_seed",
            status="quarantined",
            started_at=utcnow(),
        )
        session.add(quarantined)
        memberships[0].seed_batch_id = quarantined.id
        session.commit()
        profile = TerritoryService(
            session,
            workspace_id="workspace:first",
        ).create_profile(
            ProfileCreate(
                product_id=offer.id,
                trades=["hvac"],
                customer_kind="residential",
                market={"city": "Toronto", "radius_km": 25},
                signals=[],
                exclude=[],
                limit=25,
            )
        )

        rows = ProfileMatchService(session).match(
            profile=profile,
            niche_ids=[profile.niche_id],
            limit=25,
        )

        assert len(rows) == 1


def test_profile_signals_deliver_only_confirmed_matches() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        _niche(session, slug="home_service_hvac", label="HVAC contractors")
        _seed_hvac_businesses(session)
        businesses = list(
            session.scalars(select(BusinessModel).order_by(BusinessModel.display_name))
        )
        BusinessFactRepository(session).upsert(
            businesses[1].id,
            BusinessFactValue(
                key=BusinessFactKey.QUOTE_OR_BOOKING_FORM_PRESENT,
                value=False,
                observed_at=utcnow(),
                source_observation_id=None,
            ),
        )
        session.commit()
        profile = TerritoryService(
            session,
            workspace_id="workspace:first",
        ).create_profile(
            ProfileCreate(
                product_id=offer.id,
                trades=["hvac"],
                customer_kind="residential",
                market={"city": "Toronto", "radius_km": 25},
                signals=["no_quote_flow"],
                exclude=[],
                limit=25,
            )
        )

        rows = ProfileMatchService(session).match(
            profile=profile,
            niche_ids=[profile.niche_id],
            limit=25,
        )

        assert [row["title"] for row in rows] == [businesses[1].display_name]
        assert rows[0]["raw"]["profile_match"]["rank_position"] == 1
        assert rows[0]["raw"]["profile_match"]["matched_signal_count"] == 1
        assert rows[0]["raw"]["profile_match"]["signals"]["no_quote_flow"]["matched"] is True
        assert rows[0]["raw"]["profile_match"]["matched_signals"] == [
            {
                "signal_key": "no_quote_flow",
                "fact_key": "quote_or_booking_form_present",
                "value": False,
                "confidence": "confirmed",
            }
        ]


def test_profile_does_not_rank_staged_dynamic_signal_definition() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        _niche(session, slug="home_service_hvac", label="HVAC contractors")
        _seed_hvac_businesses(session)
        businesses = list(
            session.scalars(select(BusinessModel).order_by(BusinessModel.display_name))
        )
        definition = SignalDefinitionModel(
            id=new_id("signal"),
            key="mobile_viewport_present",
            label="Mobile viewport present",
            value_type="boolean",
            category="performance",
            status="active",
            collector_key="website_dom",
            extractor_key="payload_path",
            freshness_days=30,
            opportunity_direction="false_is_opportunity",
            config={"payload_path": "website_enrichment.has_mobile_viewport"},
            version=1,
        )
        session.add(definition)
        session.flush()
        BusinessFactRepository(session).upsert(
            businesses[0].id,
            BusinessFactValue(
                key=definition.key,
                value=False,
                observed_at=utcnow(),
                source_observation_id=None,
                quality_state="staged",
            ),
        )
        session.commit()
        profile = TerritoryService(
            session,
            workspace_id="workspace:first",
        ).create_profile(
            ProfileCreate(
                product_id=offer.id,
                trades=["hvac"],
                customer_kind="residential",
                market={"city": "Toronto", "radius_km": 25},
                signals=[definition.key],
                exclude=[],
                limit=25,
            )
        )

        rows = ProfileMatchService(session).match(
            profile=profile,
            niche_ids=[profile.niche_id],
            limit=25,
        )

        assert rows == []


def test_profile_does_not_rank_staged_probable_website_evidence() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        _niche(session, slug="home_service_hvac", label="HVAC contractors")
        _seed_hvac_businesses(session)
        business = session.scalar(
            select(BusinessModel).order_by(BusinessModel.display_name)
        )
        definition = SignalDefinitionModel(
            id=new_id("signal"),
            key="website_status",
            label="Website status",
            value_type="text",
            category="website",
            status="active",
            collector_key="website_http",
            extractor_key="website_status",
            freshness_days=30,
            opportunity_direction="missing_is_opportunity",
            config={
                "opportunity_values": [
                    "missing",
                    "not_listed",
                    "unavailable",
                    "parked",
                ]
            },
            version=1,
        )
        session.add(definition)
        session.flush()
        BusinessFactRepository(session).upsert(
            business.id,
            BusinessFactValue(
                key=definition.key,
                value="not_listed",
                observed_at=utcnow(),
                source_observation_id=None,
                confidence=65,
                resolution_state="probable",
                quality_state="staged",
            ),
        )
        session.commit()
        profile = TerritoryService(
            session,
            workspace_id="workspace:first",
        ).create_profile(
            ProfileCreate(
                product_id=offer.id,
                trades=["hvac"],
                customer_kind="residential",
                market={"city": "Toronto", "radius_km": 25},
                signals=[definition.key],
                exclude=[],
                limit=25,
            )
        )

        rows = ProfileMatchService(session).match(
            profile=profile,
            niche_ids=[profile.niche_id],
            limit=25,
        )

        assert rows == []


def test_profile_service_expands_signals_and_reports_service_evidence() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        _niche(session, slug="home_service_hvac", label="HVAC contractors")
        _seed_hvac_businesses(session)
        business = session.scalar(select(BusinessModel).order_by(BusinessModel.display_name))
        signal = SignalDefinitionModel(
            id=new_id("signal"),
            key="html_language_present",
            label="HTML language declared",
            value_type="boolean",
            category="localization",
            status="active",
            collector_key="website_dom",
            extractor_key="html_language_present",
            freshness_days=30,
            opportunity_direction="false_is_opportunity",
            config={},
            version=1,
        )
        service_definition = ServiceDefinitionModel(
            id=new_id("service"),
            key="multilingual_localization",
            label="Multilingual localization",
            status="active",
            sort_order=10,
            version=1,
        )
        service_definition.signal_mappings.append(
            ServiceSignalMappingModel(
                id=new_id("service_signal"),
                signal_definition=signal,
                weight=1.5,
                sort_order=0,
            )
        )
        session.add(service_definition)
        session.flush()
        BusinessFactRepository(session).upsert(
            business.id,
            BusinessFactValue(
                key=signal.key,
                value=False,
                observed_at=utcnow(),
                source_observation_id=None,
                quality_state="published",
            ),
        )
        session.commit()

        profile = TerritoryService(session, workspace_id="workspace:first").create_profile(
            ProfileCreate(
                product_id=offer.id,
                trades=["hvac"],
                customer_kind="residential",
                market={"city": "Toronto", "radius_km": 25},
                services=[service_definition.key],
                limit=25,
            )
        )
        rows = ProfileMatchService(session).match(
            profile=profile, niche_ids=[profile.niche_id], limit=25
        )

        assert profile.service_keys == [service_definition.key]
        assert profile.signal_keys == [signal.key]
        assert rows[0]["raw"]["profile_match"]["matched_services"] == [
            {
                "service_key": service_definition.key,
                "label": service_definition.label,
                "score": 1.5,
                "supporting_evidence": [
                    {
                        "signal_key": signal.key,
                        "fact_key": signal.key,
                        "value": False,
                        "confidence": "confirmed",
                        "weight": 1.5,
                    }
                ],
            }
        ]


def test_profile_learning_reorders_only_already_eligible_matches() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        _niche(session, slug="home_service_hvac", label="HVAC contractors")
        _seed_hvac_businesses(session)
        businesses = list(
            session.scalars(select(BusinessModel).order_by(BusinessModel.display_name))
        )
        facts = BusinessFactRepository(session)
        facts.upsert(
            businesses[0].id,
            BusinessFactValue(
                key=BusinessFactKey.QUOTE_OR_BOOKING_FORM_PRESENT,
                value=False,
                observed_at=utcnow(),
                source_observation_id=None,
            ),
        )
        facts.upsert(
            businesses[1].id,
            BusinessFactValue(
                key=BusinessFactKey.CONTACT_FORM_PRESENT,
                value=False,
                observed_at=utcnow(),
                source_observation_id=None,
            ),
        )
        profile = TerritoryService(
            session,
            workspace_id="workspace:first",
        ).create_profile(
            ProfileCreate(
                product_id=offer.id,
                trades=["hvac"],
                customer_kind="residential",
                market={"city": "Toronto", "radius_km": 25},
                signals=["no_quote_flow", "no_contact_form"],
                exclude=[],
                limit=25,
            )
        )
        session.add(
            OutcomeModel(
                id=new_id("outcome_model"),
                workspace_id="workspace:first",
                product_id=offer.id,
                niche_id=profile.niche_id,
                computed_at=utcnow(),
                n_contacted=30,
                n_positive=5,
                weights={"no_quote_flow": 0.25, "no_contact_form": 4.0},
            )
        )
        session.commit()

        rows = ProfileMatchService(session).match(
            profile=profile,
            niche_ids=[profile.niche_id],
            limit=25,
        )

        assert [row["title"] for row in rows] == [
            businesses[1].display_name,
            businesses[0].display_name,
        ]
        assert all(
            row["raw"]["profile_match"]["matched_signal_count"] == 1
            for row in rows
        )
        assert rows[0]["raw"]["profile_match"]["outcome_adjustment"] > 0
        assert rows[1]["raw"]["profile_match"]["outcome_adjustment"] < 0


def test_profile_stale_or_missing_signal_facts_do_not_enter_delivery() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        _niche(session, slug="home_service_hvac", label="HVAC contractors")
        _seed_hvac_businesses(session)
        businesses = list(
            session.scalars(select(BusinessModel).order_by(BusinessModel.display_name))
        )
        BusinessFactRepository(session).upsert(
            businesses[0].id,
            BusinessFactValue(
                key=BusinessFactKey.QUOTE_OR_BOOKING_FORM_PRESENT,
                value=False,
                observed_at=utcnow() - timedelta(days=60),
                source_observation_id=None,
            ),
        )
        session.commit()
        profile = TerritoryService(
            session,
            workspace_id="workspace:first",
        ).create_profile(
            ProfileCreate(
                product_id=offer.id,
                trades=["hvac"],
                customer_kind="residential",
                market={"city": "Toronto", "radius_km": 25},
                signals=["no_quote_flow"],
                exclude=[],
                limit=25,
            )
        )

        rows = ProfileMatchService(session).match(
            profile=profile,
            niche_ids=[profile.niche_id],
            limit=25,
        )

        assert rows == []


def test_profile_change_feed_reports_entering_and_exiting_selected_signal() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        _niche(session, slug="home_service_hvac", label="HVAC contractors")
        _seed_hvac_businesses(session)
        business = session.scalar(
            select(BusinessModel).order_by(BusinessModel.display_name).limit(1)
        )
        assert business is not None
        profile = TerritoryService(
            session,
            workspace_id="workspace:first",
        ).create_profile(
            ProfileCreate(
                product_id=offer.id,
                trades=["hvac"],
                customer_kind="residential",
                market={"city": "Toronto", "radius_km": 25},
                signals=["no_quote_flow"],
                exclude=[],
            )
        )
        observed_at = utcnow()
        facts = BusinessFactRepository(session)
        facts.upsert(
            business.id,
            BusinessFactValue(
                key=BusinessFactKey.QUOTE_OR_BOOKING_FORM_PRESENT,
                value=False,
                observed_at=observed_at,
                source_observation_id=None,
            ),
        )
        facts.upsert(
            business.id,
            BusinessFactValue(
                key=BusinessFactKey.QUOTE_OR_BOOKING_FORM_PRESENT,
                value=True,
                observed_at=observed_at + timedelta(minutes=1),
                source_observation_id=None,
            ),
        )
        session.commit()

        changes = ProfileChangeService(
            session,
            workspace_id="workspace:first",
        ).list(profile.id)

        relevant = [change for change in changes if change.business_id == business.id]
        assert [change.kind.value for change in relevant] == ["exited", "entered"]


def test_profile_website_signal_requires_confirmed_missing_evidence() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        _niche(session, slug="home_service_hvac", label="HVAC contractors")
        _seed_hvac_businesses(session)
        businesses = list(
            session.scalars(select(BusinessModel).order_by(BusinessModel.display_name))
        )
        BusinessFactRepository(session).upsert(
            businesses[1].id,
            BusinessFactValue(
                key=BusinessFactKey.WEBSITE_STATUS,
                value="missing",
                observed_at=utcnow(),
                source_observation_id=None,
            ),
        )
        session.commit()
        profile = TerritoryService(
            session,
            workspace_id="workspace:first",
        ).create_profile(
            ProfileCreate(
                product_id=offer.id,
                trades=["hvac"],
                customer_kind="residential",
                market={"city": "Toronto", "radius_km": 25},
                signals=["website_unavailable"],
                exclude=[],
                limit=25,
            )
        )

        rows = ProfileMatchService(session).match(
            profile=profile,
            niche_ids=[profile.niche_id],
            limit=25,
        )

        assert [row["title"] for row in rows] == [businesses[1].display_name]
        assert rows[0]["raw"]["profile_match"]["confirmed_signal_count"] == 1
        assert rows[0]["raw"]["profile_match"]["signals"]["website_unavailable"] == {
            "fact_key": "website_status",
            "value": "missing",
            "matched": True,
            "confidence": "confirmed",
        }
        campaign = CampaignRepository(
            session,
            workspace_id="workspace:first",
        ).create(
            CampaignCreate(
                product_id=offer.id,
                territory_id=profile.id,
                name="Website confidence delivery",
                max_leads=25,
            )
        )
        service = CampaignService.__new__(CampaignService)
        service.session = session
        service.campaigns = CampaignRepository(
            session,
            workspace_id="workspace:first",
        )
        service.leads = LeadRepository(
            session,
            workspace_id="workspace:first",
        )

        leads = service.materialize_profile_matches(campaign.id, rows)

        assert [lead.qualification.fit_status for lead in leads if lead.qualification] == [
            AgentFitStatus.GOOD_FIT,
        ]


def test_profile_signals_rank_by_confirmed_match_count_before_distance() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        _niche(session, slug="home_service_hvac", label="HVAC contractors")
        _seed_hvac_businesses(session)
        businesses = list(
            session.scalars(select(BusinessModel).order_by(BusinessModel.display_name))
        )
        facts = BusinessFactRepository(session)
        for business in businesses:
            facts.upsert(
                business.id,
                BusinessFactValue(
                    key=BusinessFactKey.QUOTE_OR_BOOKING_FORM_PRESENT,
                    value=False,
                    observed_at=utcnow(),
                    source_observation_id=None,
                ),
            )
        facts.upsert(
            businesses[1].id,
            BusinessFactValue(
                key=BusinessFactKey.CONTACT_FORM_PRESENT,
                value=False,
                observed_at=utcnow(),
                source_observation_id=None,
            ),
        )
        session.commit()
        profile = TerritoryService(
            session,
            workspace_id="workspace:first",
        ).create_profile(
            ProfileCreate(
                product_id=offer.id,
                trades=["hvac"],
                customer_kind="residential",
                market={"city": "Toronto", "radius_km": 25},
                signals=["no_quote_flow", "no_contact_form"],
                exclude=[],
                limit=25,
            )
        )

        rows = ProfileMatchService(session).match(
            profile=profile,
            niche_ids=[profile.niche_id],
            limit=25,
        )

        assert [row["title"] for row in rows] == [
            businesses[1].display_name,
            businesses[0].display_name,
        ]
        assert [
            row["raw"]["profile_match"]["matched_signal_count"] for row in rows
        ] == [2, 1]


def test_profile_materialization_qualifies_only_confirmed_signal_rows() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        _niche(session, slug="home_service_hvac", label="HVAC contractors")
        _seed_hvac_businesses(session)
        business = session.scalar(
            select(BusinessModel).order_by(BusinessModel.display_name).limit(1)
        )
        assert business is not None
        BusinessFactRepository(session).upsert(
            business.id,
            BusinessFactValue(
                key=BusinessFactKey.QUOTE_OR_BOOKING_FORM_PRESENT,
                value=False,
                observed_at=utcnow(),
                source_observation_id=None,
            ),
        )
        session.commit()
        profile = TerritoryService(
            session,
            workspace_id="workspace:first",
        ).create_profile(
            ProfileCreate(
                product_id=offer.id,
                trades=["hvac"],
                customer_kind="residential",
                market={"city": "Toronto", "radius_km": 25},
                signals=["no_quote_flow"],
                exclude=[],
                limit=25,
            )
        )
        rows = ProfileMatchService(session).match(
            profile=profile,
            niche_ids=[profile.niche_id],
            limit=25,
        )
        campaign = CampaignRepository(
            session,
            workspace_id="workspace:first",
        ).create(
            CampaignCreate(
                product_id=offer.id,
                territory_id=profile.id,
                name="Confirmed signal delivery",
                max_leads=25,
            )
        )
        service = CampaignService.__new__(CampaignService)
        service.session = session
        service.campaigns = CampaignRepository(
            session,
            workspace_id="workspace:first",
        )
        service.leads = LeadRepository(
            session,
            workspace_id="workspace:first",
        )

        leads = service.materialize_profile_matches(campaign.id, rows)

        assert len(leads) == 1
        assert leads[0].qualification is not None
        assert leads[0].qualification.qualified is True
        assert leads[0].qualification.fit_status == AgentFitStatus.GOOD_FIT
        assert leads[0].qualification.positive_signals == [
            "no_quote_flow: quote_or_booking_form_present=false"
        ]

        general_profile = TerritoryService(
            session,
            workspace_id="workspace:first",
        ).create_profile(
            ProfileCreate(
                product_id=offer.id,
                trades=["hvac"],
                customer_kind="residential",
                market={"city": "Toronto", "radius_km": 25},
                signals=[],
                exclude=[],
                limit=25,
            )
        )
        general_rows = ProfileMatchService(session).match(
            profile=general_profile,
            niche_ids=[general_profile.niche_id],
            limit=25,
        )
        general_campaign = service.campaigns.create(
            CampaignCreate(
                product_id=offer.id,
                territory_id=general_profile.id,
                name="General business delivery",
                max_leads=25,
            )
        )

        general_leads = service.materialize_profile_matches(
            general_campaign.id,
            general_rows,
        )

        assert len(general_leads) == 2
        assert all(
            lead.qualification is not None
            and lead.qualification.qualified is False
            and lead.qualification.fit_status == AgentFitStatus.MAYBE
            for lead in general_leads
        )



def test_profile_closed_filter_uses_canonical_business_status() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        _niche(session, slug="home_service_hvac", label="HVAC contractors")
        _seed_hvac_businesses(session)
        businesses = list(
            session.scalars(select(BusinessModel).order_by(BusinessModel.display_name))
        )
        businesses[0].status = "closed"
        BusinessFactRepository(session).upsert(
            businesses[0].id,
            BusinessFactValue(
                key=BusinessFactKey.BUSINESS_OPERATIONAL,
                value=True,
                observed_at=utcnow(),
                source_observation_id=None,
            ),
        )
        session.commit()
        profile = TerritoryService(
            session,
            workspace_id="workspace:first",
        ).create_profile(
            ProfileCreate(
                product_id=offer.id,
                trades=["hvac"],
                customer_kind="residential",
                market={"city": "Toronto", "radius_km": 25},
                signals=[],
                exclude=["closed"],
                limit=25,
            )
        )

        rows = ProfileMatchService(session).match(
            profile=profile,
            niche_ids=[profile.niche_id],
            limit=25,
        )

        assert [row["title"] for row in rows] == [businesses[1].display_name]


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
        run = session.get(AudienceRunModel, jobs[0].payload["audience_run_id"])
        assert run is not None
        assert run.audience_id == territory.id



def test_existing_search_can_be_attached_to_territory() -> None:
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
        campaigns = CampaignRepository(session, workspace_id="workspace:first")
        campaign = campaigns.create(
            CampaignCreate(product_id=offer.id, name="HVAC Toronto", max_leads=10)
        )
        lead = LeadRepository(session, workspace_id="workspace:first").create_from_seed(
            campaign.id,
            offer.id,
            LeadSeedInput(company_name="Existing HVAC", geography="Toronto"),
        )
        outcome = OutcomeService(session, workspace_id="workspace:first").record(
            lead.id,
            LeadOutcomeCreate(outcome=LeadOutcome.CONTACTED, channel=OutcomeChannel.EMAIL),
        )

        campaigns.update(campaign.id, CampaignUpdate(territory_id=territory.id))

        assert campaigns.get(campaign.id).territory_id == territory.id
        assert LeadRepository(session, workspace_id="workspace:first").get(lead.id).territory_id == territory.id
        attached_outcome = session.get(LeadOutcomeModel, outcome.id)
        assert attached_outcome is not None
        assert attached_outcome.territory_id == territory.id
        assert attached_outcome.niche_id == territory.niche_id
        assert attached_outcome.market_key == territory.market_key


def test_territory_metrics_report_coverage_and_conversion() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        niche = _niche(session, slug="home_service_hvac", label="HVAC contractors")
        _seed_hvac_businesses(session)
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
        run_service = AudienceRunService(session, workspace_id="workspace:first")
        run = run_service.create(territory.id)
        run_service.process(run.id)
        results = list(
            session.scalars(
                select(AudienceResultModel)
                .where(AudienceResultModel.run_id == run.id)
                .order_by(AudienceResultModel.rank_position)
            )
        )
        assert len(results) == 2
        lead = AudienceOutreachService(
            session,
            workspace_id="workspace:first",
        ).promote(results[0].id)
        outcomes = OutcomeService(session, workspace_id="workspace:first")
        outcomes.record(
            lead.id,
            LeadOutcomeCreate(
                outcome=LeadOutcome.CONTACTED,
                channel=OutcomeChannel.EMAIL,
            ),
        )
        outcomes.record(
            lead.id,
            LeadOutcomeCreate(
                outcome=LeadOutcome.REPLIED_POSITIVE,
                channel=OutcomeChannel.EMAIL,
            ),
        )
        outcomes.record(
            lead.id,
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


def _seed_hvac_businesses(session) -> None:
    canonical = CanonicalRepository(session)
    for index in (1, 2):
        canonical.upsert_from_discovery_result(
            company_name=f"HVAC {index}",
            contact_email=f"owner{index}@hvac-{index}.example",
            geography="Toronto",
            description="Independent HVAC contractor",
            source="google_places",
            raw={
                "id": f"places/hvac-{index}",
                "businessStatus": "OPERATIONAL",
                "location": {
                    "latitude": 43.6532 + index / 1000,
                    "longitude": -79.3832 + index / 1000,
                },
                "nationalPhoneNumber": f"416-555-010{index}",
                "website_presence": {"status": "no_website_found"},
                "source_request_intent": {
                    "business_category": "HVAC contractors",
                    "location": "Toronto",
                    "search_query": "HVAC contractors in Toronto",
                },
            },
        )
    now = utcnow()
    for membership in session.scalars(select(BusinessNicheMembershipModel)):
        for dimension, confidence in {
            "identity": 90,
            "business_identity": 85,
            "trade": 90,
            "location": 85,
        }.items():
            session.add(
                ValidationResultModel(
                    id=new_id("validation"),
                    idempotency_key=(
                        f"{membership.business_id}:{membership.niche_id}:"
                        f"{membership.market_key}:{dimension}"
                    ),
                    business_id=membership.business_id,
                    niche_id=membership.niche_id,
                    market_key=membership.market_key,
                    validation_type=dimension,
                    status="passed",
                    confidence=confidence,
                    reason="Test validation passed.",
                    evidence=[],
                    validator="test",
                    validator_version=1,
                    observed_at=now,
                    expires_at=now + timedelta(days=30),
                )
            )
    session.commit()
