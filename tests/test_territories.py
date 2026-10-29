from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

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
from business_index.pipeline import BusinessIndexPipelineService
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
from job_queue.schemas import JobType
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
from leads.workspace import WorkspaceLeadService
from leads.schemas import (
    AgentFitStatus,
    ContactPolicyStatus,
    LeadContactPolicyUpdate,
    LeadUpdate,
    SuppressionScope,
)
from outcomes.schemas import LeadOutcome, LeadOutcomeCreate, OutcomeChannel
from outcomes.service import OutcomeService
from territories.metrics import TerritoryMetricsService
from territories.matching import ProfileMatchService
from territories.folders import AudienceFolderService
from territories.schemas import AudienceFolderCreate
from territories.coordinate_backfill import CoordinateBackfillService
from territories.geocoding import GeocodedMarket, MarketGeocoder


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


def test_audience_folders_are_optional_and_deletion_preserves_audiences() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        niche = _niche(session, slug="home_service_hvac", label="HVAC contractors")
        folders = AudienceFolderService(session, workspace_id="workspace:first")
        folder = folders.create(
            AudienceFolderCreate(product_id=offer.id, name=" Priority trades ")
        )
        territory_service = TerritoryService(session, workspace_id="workspace:first")
        territory = territory_service.create(
            TerritoryCreate(
                product_id=offer.id,
                folder_id=folder.id,
                niche_id=niche.id,
                niche_slug=niche.slug,
                niche_label=niche.label,
                market_key="Toronto",
                confirmed=True,
            )
        )

        listed = folders.list(product_id=offer.id)
        assert listed[0].name == "Priority trades"
        assert listed[0].audience_count == 1
        assert territory_service.get_read(territory.id).folder_id == folder.id

        folders.delete(folder.id)

        assert territory_service.get_read(territory.id).folder_id is None


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
            _profile_create(session,
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
        assert result.audience.niche_label == "Painting contractors"
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
            _profile_create(session,
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
        data = _profile_create(session,
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
                _profile_create(session,
                    product_id=offer.id,
                    trades=["painters"],
                    customer_kind="residential",
                    market={"city": "Toronto", "radius_km": 25},
                ),
                session,
                auth,
            )


def test_profile_source_expansion_queues_the_selected_niche_once() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        profile = TerritoryService(
            session,
            workspace_id="workspace:first",
        ).create_profile(
            _profile_create(session,
                product_id=offer.id,
                trades=["painters"],
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
        assert len(first) == 1
        assert len(segments) == 1
        assert len(jobs) == 1
        assert all(segment.target_business_count == 100 for segment in segments)
        assert all(segment.demand_count == 1 for segment in segments)
        assert all(
            [task["provider_id"] for task in segment.source_plan] == ["openstreetmap"]
            for segment in segments
        )


def test_profile_source_expansion_skips_segments_without_a_provider() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        profile = TerritoryService(
            session,
            workspace_id="workspace:first",
        ).create_profile(
            _profile_create(session,
                product_id=offer.id,
                trades=["painters"],
                customer_kind="residential",
                market={"city": "Toronto", "radius_km": 25},
                limit=25,
            )
        )

        segment_ids = enqueue_profile_source_expansion(
            session,
            profile,
            google_places_configured=False,
            search_configured=False,
            openstreetmap_enabled=False,
            apify_sources=[],
            source_recipes=[],
        )

        assert segment_ids == []
        assert session.scalar(
            select(func.count()).select_from(BusinessIndexSegmentModel)
        ) == 0
        assert session.scalar(select(func.count()).select_from(QueueJobModel)) == 0


def test_profile_batch_distinguishes_scoring_retrying_and_failed() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        auth = SimpleNamespace(workspace_id="workspace:first")
        result = create_profile_route(
            _profile_create(session,
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
        assert completed.state.value == "scoring"
        assert completed.failure_class is None

        job = session.get(QueueJobModel, result.job.id)
        assert job is not None
        assert job.status == "queued"

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
        assert repaired.state.value == "scoring"
        assert initial_run.state == "waiting_validation"
        assert job.status == "queued"

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


def test_profile_contract_accepts_dynamic_niches_and_bounded_custom_sizes() -> None:
    valid = {
        "product_id": "product_1",
        "niche_id": "niche_1",
        "customer_kind": "both",
        "market": {
            "place_label": "Toronto, Ontario, Canada",
            "place_provider": "test",
            "latitude": 43.6532,
            "longitude": -79.3832,
            "radius_km": 100,
        },
        "limit": 10,
    }

    parsed = ProfileCreate.model_validate(valid)
    assert parsed.niche_id == "niche_1"
    assert parsed.customer_kind.value == "both"
    assert parsed.market.radius_km == 100
    assert parsed.limit == 10

    with pytest.raises(ValueError):
        ProfileCreate.model_validate({key: value for key, value in valid.items() if key != "niche_id"})
    with pytest.raises(ValueError):
        ProfileCreate.model_validate(
            {**valid, "market": {**valid["market"], "place_label": "United States, Canada"}}
        )
    with pytest.raises(ValueError):
        ProfileCreate.model_validate({**valid, "market": {**valid["market"], "radius_km": 251}})
    with pytest.raises(ValueError):
        ProfileCreate.model_validate({**valid, "limit": 101})


def test_profile_options_come_from_backend_capabilities_and_hide_disabled_niches() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        painting = _niche(session, slug="home_service_painting", label="Painting contractors")
        disabled = _niche(session, slug="home_service_plumbing", label="Plumbing contractors")
        disabled.active = False
        session.commit()
        service = TerritoryService(session, workspace_id="workspace:first")

        assert service.profile_options() == [{
            "id": painting.id,
            "key": "home_service_painting",
            "label": "Painting contractors",
            "category": "Painting contractors",
        }]


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


def test_profile_persists_one_niche_and_supports_both_customer_kinds() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        profile = TerritoryService(
            session, workspace_id="workspace:first"
        ).create_profile(
            _profile_create(session,
                product_id=offer.id,
                trades=["painters"],
                customer_kind="both",
                market={"city": "Toronto", "radius_km": 50},
                limit=40,
            )
        )

        assert profile.niche.slug == "home_service_painting"
        assert profile.customer_kind == "both"
        assert profile.radius_km == 50
        assert profile.batch_size == 40
        assert profile.refill_policy == "when_depleted"
        assert profile.label == "Painting contractors near Toronto"


def test_profile_criteria_edit_increments_version_and_rehashes() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        service = TerritoryService(session, workspace_id="workspace:first")
        profile = service.create_profile(
            _profile_create(session,
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


def test_profile_edit_can_change_niche_customer_kind_and_canonical_place() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        painters = _niche(
            session,
            slug="home_service_painting",
            label="Painting contractors",
        )
        hvac = _niche(
            session,
            slug="home_service_hvac",
            label="HVAC contractors",
        )
        geocoder = SimpleNamespace(
            resolve=lambda location: GeocodedMarket(
                latitude=30.2672,
                longitude=-97.7431,
                label="Austin, Travis County, Texas, United States",
                provider="test",
                external_id="place:austin",
                country_code="us",
            )
        )
        service = TerritoryService(
            session,
            workspace_id="workspace:first",
            market_geocoder=geocoder,
        )
        profile = service.create(
            TerritoryCreate(
                product_id=offer.id,
                niche_id=painters.id,
                niche_slug=painters.slug,
                niche_label=painters.label,
                market_key="Toronto",
                city="Toronto",
                latitude=43.6532,
                longitude=-79.3832,
                service_keys=["website_modernization"],
                confirmed=True,
            )
        )

        updated = service.update(
            profile.id,
            TerritoryUpdate(
                niche_id=hvac.id,
                customer_kind="both",
                place_label="Austin, Texas, United States",
                radius_km=50,
            ),
        )

        assert updated.niche_id == hvac.id
        assert updated.customer_kind == "both"
        assert updated.city == "Austin"
        assert updated.place_external_id == "place:austin"
        assert updated.country_code == "us"
        assert (updated.latitude, updated.longitude) == (30.2672, -97.7431)
        assert updated.radius_km == 50


def test_profile_clone_creates_a_distinct_audience_with_the_same_criteria() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        service = TerritoryService(session, workspace_id="workspace:first")
        original_input = _profile_create(
            session,
            product_id=offer.id,
            trades=["painters"],
            customer_kind="both",
            market={"city": "Toronto", "radius_km": 25},
            name="Toronto painters",
        )

        original = service.create_profile(original_input)
        clone = service.create_profile(
            original_input.model_copy(
                update={
                    "name": "Toronto painters copy",
                    "clone_from_id": original.id,
                }
            )
        )

        assert clone.id != original.id
        assert clone.niche_id == original.niche_id
        assert clone.customer_kind == original.customer_kind
        assert clone.place_label == original.place_label
        assert clone.radius_km == original.radius_km
        assert clone.label == "Toronto painters copy"


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


def test_profile_niche_id_is_authoritative() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        _niche(session, slug="home_service_hvac", label="HVAC contractors")
        painters = _niche(
            session,
            slug="home_service_painting",
            label="Painting contractors",
        )
        profile = TerritoryService(
            session, workspace_id="workspace:first"
        ).create_profile(
            _profile_create(session,
                product_id=offer.id,
                trades=["hvac"],
                customer_kind="residential",
                market={"city": "Toronto", "radius_km": 25},
            )
        )
        profile.niche_id = painters.id
        session.commit()

        assert [niche.id for niche in _territory_niches(session, profile)] == [painters.id]


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
            _profile_create(session,
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


def test_dismissed_business_stays_out_of_refills_and_can_be_restored() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        _niche(session, slug="home_service_hvac", label="HVAC contractors")
        _seed_hvac_businesses(session)
        profile = TerritoryService(
            session,
            workspace_id="workspace:first",
        ).create_profile(
            _profile_create(
                session,
                product_id=offer.id,
                trades=["hvac"],
                customer_kind="residential",
                market={"city": "Toronto", "radius_km": 25},
                signals=[],
                exclude=[],
                limit=1,
            )
        )
        profile.batch_size = 1
        session.commit()
        service = AudienceRunService(session, workspace_id="workspace:first")

        first_run = service.create(profile.id)
        service.process(first_run.id)
        dismissed = service.get_read(first_run.id).results[0]
        service.update_result(
            dismissed.id,
            AudienceResultUpdate(review_status="not_fit"),
        )

        replacement_run = service.create(profile.id)
        service.process(replacement_run.id)
        replacement = service.get_read(replacement_run.id).results

        assert len(replacement) == 1
        assert replacement[0].business_id != dismissed.business_id
        visible = service.latest_leads_for_audience(profile.id)
        assert {lead.business_id for lead in visible} == {
            replacement[0].business_id,
            dismissed.business_id,
        }
        assert next(
            lead for lead in visible if lead.business_id == dismissed.business_id
        ).review_status.value == "not_fit"

        service.update_result(
            dismissed.id,
            AudienceResultUpdate(review_status="unreviewed"),
        )

        restored = service.latest_leads_for_audience(profile.id)
        assert next(
            lead for lead in restored if lead.business_id == dismissed.business_id
        ).review_status.value == "unreviewed"


def test_audience_run_requests_coverage_and_waits_until_deadline() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        _niche(session, slug="home_service_hvac", label="HVAC contractors")
        _seed_hvac_businesses(session)
        profile = TerritoryService(
            session,
            workspace_id="workspace:first",
        ).create_profile(
            _profile_create(session,
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

        assert run.state == "waiting_validation"
        assert run.result_count == 2
        assert run.completed_at is None
        assert needs_expansion is True
        assert len(service.latest_leads_for_audience(profile.id)) == 2
        coverage = session.scalar(select(CoverageRequestModel))
        assert coverage is not None
        assert coverage.status == "queued"
        assert coverage.requested_count == 23

        # A background retry moves the run through matching again. Results
        # already accepted for this run must remain visible while it does so.
        run.state = "matching"
        session.commit()
        assert len(service.latest_leads_for_audience(profile.id)) == 2

        run.state = "expanding"
        session.commit()
        assert len(service.latest_leads_for_audience(profile.id)) == 2

        run.state = "waiting_validation"
        session.commit()

        run, needs_expansion = service.process(run.id)

        assert run.state == "waiting_validation"
        assert needs_expansion is True

        coverage.status = "processing"
        session.commit()
        run, needs_expansion = service.process(run.id)

        assert run.state == "waiting_validation"
        assert needs_expansion is False

        run.deadline_at = utcnow() - timedelta(seconds=1)
        session.commit()
        run, needs_expansion = service.process(run.id)

        assert run.state == "partial"
        assert run.completed_at is not None
        assert needs_expansion is False
        assert coverage.status == "completed"


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
            _profile_create(session,
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
            _profile_create(session,
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
            _profile_create(session,
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
            _profile_create(session,
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
            _profile_create(session,
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


def test_profile_match_uses_the_signal_fact_observation_as_its_source() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        _niche(session, slug="home_service_hvac", label="HVAC contractors")
        _seed_hvac_businesses(session)
        business = list(
            session.scalars(select(BusinessModel).order_by(BusinessModel.display_name))
        )[1]
        canonical = CanonicalRepository(session)
        website_evidence = canonical.record_business_evidence(
            business=business,
            source="company_website_signal",
            raw={
                "source": "company_website_signal",
                "source_url": "https://hvac.example/contact",
                "website_enrichment": {"has_quote_form": False},
            },
        )
        canonical.record_business_evidence(
            business=business,
            source="pagespeed_mobile",
            raw={
                "source": "pagespeed_mobile",
                "source_url": "https://hvac.example",
                "pagespeed_mobile": {"performance_score": 62},
            },
        )
        BusinessFactRepository(session).upsert(
            business.id,
            BusinessFactValue(
                key=BusinessFactKey.QUOTE_OR_BOOKING_FORM_PRESENT,
                value=False,
                observed_at=utcnow(),
                source_observation_id=website_evidence.source_observation_id,
            ),
        )
        session.commit()
        profile = TerritoryService(
            session,
            workspace_id="workspace:first",
        ).create_profile(
            _profile_create(
                session,
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

        assert rows[0]["source"] == "company_website_signal"
        matched = rows[0]["raw"]["profile_match"]["matched_signals"][0]
        assert matched["source"] == "company_website_signal"
        assert matched["source_observation_id"] == website_evidence.source_observation_id
        assert matched["source_url"] == "https://hvac.example/contact"


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
            _profile_create(session,
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
        run = AudienceRunService(
            session,
            workspace_id="workspace:first",
        ).create(profile.id)
        processed, _ = AudienceRunService(
            session,
            workspace_id="workspace:first",
        ).process(run.id)
        collection_jobs = list(
            session.scalars(
                select(QueueJobModel).where(
                    QueueJobModel.type == JobType.SIGNAL_COLLECTION.value
                )
            )
        )
        assert processed.state == "waiting_validation"
        assert len(collection_jobs) == 1
        assert collection_jobs[0].payload["signal_definition_id"] == definition.id
        assert collection_jobs[0].payload["business_ids"] == [businesses[0].id]
        assert collection_jobs[0].payload["reason"] == (
            "audience_staged_fact_validation"
        )


def test_opportunity_audit_handoff_queues_only_waiting_audience_signals() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        niche = _niche(
            session,
            slug="home_service_hvac",
            label="HVAC contractors",
        )
        requested = SignalDefinitionModel(
            id=new_id("signal"),
            key="contact_form_present",
            label="Contact form present",
            value_type="boolean",
            category="conversion",
            status="active",
            collector_key="website_dom",
            extractor_key="payload_path",
            freshness_days=30,
            opportunity_direction="false_is_opportunity",
            config={"payload_path": "website_enrichment.has_contact_form"},
            version=1,
        )
        unrelated = SignalDefinitionModel(
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
        session.add_all([requested, unrelated])
        session.commit()
        audience = TerritoryService(
            session,
            workspace_id="workspace:first",
        ).create_profile(
            _profile_create(
                session,
                product_id=offer.id,
                trades=["hvac"],
                customer_kind="residential",
                market={"city": "Toronto", "radius_km": 25},
                signals=[requested.key],
                exclude=[],
                limit=25,
            )
        )
        run = AudienceRunService(
            session,
            workspace_id="workspace:first",
        ).create(audience.id)
        run.state = "waiting_validation"
        segment = BusinessIndexSegmentModel(
            id=new_id("index_segment"),
            niche_id=niche.id,
            market_key=audience.market_key,
            market_label=audience.city,
            status="active",
            demand_count=1,
            target_business_count=25,
            source_plan=[],
            source_state={},
        )
        session.add(segment)
        session.add(
            CoverageRequestModel(
                id=new_id("coverage"),
                run_id=run.id,
                audience_id=audience.id,
                niche_id=niche.id,
                market_key=audience.market_key,
                requested_count=25,
                status="processing",
            )
        )
        session.commit()

        pipeline = object.__new__(BusinessIndexPipelineService)
        pipeline.session = session
        pipeline.queue = QueueService(session)
        count = pipeline._enqueue_requested_signal_collection(
            segment,
            business_id="business:target",
        )

        jobs = list(
            session.scalars(
                select(QueueJobModel).where(
                    QueueJobModel.type == JobType.SIGNAL_COLLECTION.value
                )
            )
        )
        assert count == 1
        assert len(jobs) == 1
        assert jobs[0].payload["signal_definition_id"] == requested.id
        assert jobs[0].payload["business_ids"] == ["business:target"]
        assert jobs[0].payload["reason"] == "audience_coverage_validation"


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
            _profile_create(session,
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
            _profile_create(session,
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
            _profile_create(session,
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
            _profile_create(session,
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
            _profile_create(session,
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
            _profile_create(session,
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
            _profile_create(session,
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
        scores = [row["raw"]["profile_match"]["opportunity_score"] for row in rows]
        assert scores[0] > scores[1]
        assert set(rows[0]["raw"]["profile_match"]["score_breakdown"]) == {
            "severity",
            "confidence",
            "freshness",
        }


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
            _profile_create(session,
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
            _profile_create(session,
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
            _profile_create(session,
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


def test_unassigned_lead_can_be_assigned_to_an_audience() -> None:
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
        campaign = CampaignRepository(session, workspace_id="workspace:first").create(
            CampaignCreate(product_id=offer.id, name="Unassigned leads", max_leads=10)
        )
        repository = LeadRepository(session, workspace_id="workspace:first")
        lead = repository.create_from_seed(
            campaign.id,
            offer.id,
            LeadSeedInput(company_name="Unassigned HVAC", geography="Toronto"),
        )

        assigned = repository.update(lead.id, LeadUpdate(territory_id=territory.id))

        assert assigned.territory_id == territory.id


def test_workspace_lead_read_model_returns_counts_and_one_page() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        campaign = CampaignRepository(session, workspace_id="workspace:first").create(
            CampaignCreate(product_id=offer.id, name="Workspace leads", max_leads=10)
        )
        repository = LeadRepository(session, workspace_id="workspace:first")
        active = repository.create_from_seed(
            campaign.id,
            offer.id,
            LeadSeedInput(company_name="Active Painting", geography="Toronto"),
        )
        dismissed = repository.create_from_seed(
            campaign.id,
            offer.id,
            LeadSeedInput(company_name="Dismissed Painting", geography="Toronto"),
        )
        repository.update(
            dismissed.id,
            LeadUpdate(review_status="not_fit"),
        )
        service = WorkspaceLeadService(session, workspace_id="workspace:first")

        counts = service.counts()
        page = service.page(view="inbox", limit=1)

        assert counts.leads == 1
        assert counts.dismissed == 1
        assert counts.all == 2
        assert page.total == 1
        assert page.items[0].id == active.id


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
        run_service.update_result(
            results[0].id,
            AudienceResultUpdate(shortlisted=True),
        )
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
        assert metrics.totals.shortlisted == 1
        assert metrics.totals.contacted == 1
        assert metrics.totals.meetings == 1
        assert metrics.totals.positive_reply_rate == 1.0
        assert metrics.totals.outcome_coverage == 0.5
        summary = TerritoryMetricsService(
            session,
            workspace_id="workspace:first",
        ).audience_performance(product_id=offer.id)
        assert len(summary) == 1
        assert summary[0].lead_count == 2
        assert summary[0].shortlisted_count == 1
        assert summary[0].contacted_count == 1
        assert summary[0].shortlist_rate == 0.5
        assert summary[0].contact_rate == 0.5


def test_overlapping_radius_audiences_reuse_one_business_with_distinct_distances() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        _niche(
            session,
            slug="home_service_painting",
            label="Residential painters",
        )
        canonical = CanonicalRepository(session)
        located = canonical.upsert_from_discovery_result(
            company_name="Overlap Painter",
            geography="Scarborough, ON",
            source="google_places",
            raw={
                "id": "places/overlap-painter",
                "formattedAddress": "123 Kingston Rd, Scarborough, ON",
                "location": {"latitude": 43.75, "longitude": -79.28},
                "source_request_intent": {
                    "business_category": "Residential painters",
                    "location": "Toronto",
                    "search_query": "Residential painters in Toronto",
                },
            },
        )
        missing_coordinates = canonical.upsert_from_discovery_result(
            company_name="Unlocated Painter",
            geography="Toronto, ON",
            source="directory",
            raw={
                "external_id": "directory:unlocated-painter",
                "source_request_intent": {
                    "business_category": "Residential painters",
                    "location": "Toronto",
                    "search_query": "Residential painters in Toronto",
                },
            },
        )
        _validate_business_memberships(session)
        service = TerritoryService(session, workspace_id="workspace:first")
        toronto = service.create_profile(
            _profile_create(session,
                product_id=offer.id,
                trades=["painters"],
                customer_kind="residential",
                market={"city": "Toronto", "radius_km": 25},
                signals=[],
                exclude=[],
                limit=15,
            )
        )
        scarborough = service.create_profile(
            _profile_create(session,
                product_id=offer.id,
                trades=["painters"],
                customer_kind="residential",
                market={"city": "Scarborough", "radius_km": 10},
                signals=[],
                exclude=[],
                limit=15,
            )
        )
        runs = AudienceRunService(session, workspace_id="workspace:first")
        toronto_run = runs.create(toronto.id)
        scarborough_run = runs.create(scarborough.id)

        runs.process(toronto_run.id)
        runs.process(scarborough_run.id)

        results = list(
            session.scalars(
                select(AudienceResultModel).order_by(AudienceResultModel.audience_id)
            )
        )
        assert len(results) == 2
        assert {result.business_id for result in results} == {located.business_id}
        assert missing_coordinates.business_id not in {
            result.business_id for result in results
        }
        distances = [
            result.match_snapshot["raw"]["profile_match"]["distance_km"]
            for result in results
        ]
        assert all(distance is not None for distance in distances)
        assert distances[0] != distances[1]
        assert session.scalar(select(func.count()).select_from(BusinessModel)) == 2


def test_profile_creation_persists_geocoded_center_for_an_arbitrary_city() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        _niche(session, slug="home_service_painting", label="Residential painters")
        geocoder = SimpleNamespace(
            resolve=lambda location: GeocodedMarket(
                latitude=30.2672,
                longitude=-97.7431,
                label="Austin, Texas, United States",
                provider="test",
            )
        )

        audience = TerritoryService(
            session,
            workspace_id="workspace:first",
            market_geocoder=geocoder,
        ).create_profile(
            _profile_create(session,
                product_id=offer.id,
                trades=["painters"],
                customer_kind="residential",
                market={"city": "Austin, TX", "radius_km": 25},
                signals=[],
                exclude=[],
                limit=15,
            )
        )

        assert audience.city == "Austin"
        assert audience.place_label == "Austin, Texas, United States"
        assert audience.latitude == 30.2672
        assert audience.longitude == -97.7431


def test_coordinate_backfill_is_dry_run_first_and_uses_provider_evidence() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        niche = _niche(session, slug="home_service_hvac", label="HVAC contractors")
        audience = TerritoryService(session, workspace_id="workspace:first").create(
            TerritoryCreate(
                product_id=offer.id,
                niche_id=niche.id,
                niche_slug=niche.slug,
                niche_label=niche.label,
                market_key="Toronto",
                city="Toronto",
                confirmed=True,
            )
        )
        link = CanonicalRepository(session).upsert_from_discovery_result(
            company_name="Provider Located HVAC",
            geography="Toronto, ON",
            source="google_places",
            raw={
                "id": "places/provider-located-hvac",
                "location": {"latitude": 43.67, "longitude": -79.4},
            },
        )
        business = session.get(BusinessModel, link.business_id)
        business.latitude = None
        business.longitude = None
        session.commit()

        backfill = CoordinateBackfillService(
            session,
            geocoder=MarketGeocoder(openstreetmap_enabled=False),
        )
        dry_run = backfill.run(dry_run=True)

        assert dry_run.audiences_backfilled == 1
        assert dry_run.businesses_backfilled == 1
        assert audience.latitude is None
        assert business.latitude is None

        applied = backfill.run(dry_run=False)
        session.refresh(audience)
        session.refresh(business)

        assert applied.audiences_backfilled == 1
        assert applied.businesses_backfilled == 1
        assert (audience.latitude, audience.longitude) == (43.6532, -79.3832)
        assert (business.latitude, business.longitude) == (43.67, -79.4)


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


def _profile_create(
    session,
    *,
    product_id: str,
    trades: list[str],
    customer_kind: str,
    market: dict[str, Any],
    **values: Any,
) -> ProfileCreate:
    trade = trades[0]
    definitions = {
        "painters": ("home_service_painting", "Painting contractors"),
        "hvac": ("home_service_hvac", "HVAC contractors"),
        "roofers": ("home_service_roofing", "Roofing contractors"),
    }
    slug, label = definitions[trade]
    niche = session.scalar(select(NicheModel).where(NicheModel.slug == slug))
    if niche is None:
        niche = _niche(session, slug=slug, label=label)
    place_label = str(market["city"])
    coordinates = {
        "Toronto": (43.6532, -79.3832),
        "Scarborough": (43.7764, -79.2318),
        "Austin, TX": (30.2672, -97.7431),
    }.get(place_label, (43.6532, -79.3832))
    return ProfileCreate(
        product_id=product_id,
        niche_id=niche.id,
        customer_kind=customer_kind,
        market={
            "place_label": place_label,
            "place_provider": "market_cache",
            "latitude": coordinates[0],
            "longitude": coordinates[1],
            "radius_km": market["radius_km"],
        },
        **values,
    )


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

    _validate_business_memberships(session)


def _validate_business_memberships(session) -> None:
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
