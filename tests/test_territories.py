from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
import pytest

from campaigns.repository import CampaignRepository
from business_facts.repository import (
    BusinessFactKey,
    BusinessFactRepository,
    BusinessFactValue,
)
from business_index.schemas import SearchContract
from campaigns.schemas import CampaignCreate, CampaignUpdate, LeadSeedInput
from canonical.repository import CanonicalRepository
from db.models import (
    BusinessModel,
    CampaignModel,
    LeadModel,
    LeadOutcomeModel,
    NicheModel,
    ProfileDeliveryItemModel,
    QueueJobModel,
    TerritoryDeliveryModel,
    TerritoryModel,
)
from db.session import create_database
from products.repository import ProductRepository
from products.schemas import ProductCreate, QualificationCriterion
from shared.errors import ConflictError, NotFoundError, ValidationError
from shared.utils import new_id, utcnow
from territories.routes import (
    create_profile as create_profile_route,
    current_profile_batch,
)
from territories.schemas import (
    ProfileCreate,
    TerritoryCreate,
    TerritoryRefillPolicy,
    TerritoryResolveRequest,
    TerritoryUpdate,
)
from territories.service import TerritoryService
from territories.dedupe import exclude_previously_delivered_rows
from territories.refresh import (
    TerritoryRefreshService,
    _merge_niche_rows,
    _territory_contract,
)
from territories.refill import enqueue_refill_if_depleted
from territories.scheduler import enqueue_due_territories
from leads.repository import LeadRepository
from leads.schemas import AgentFitStatus, QualificationResult
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

        assert result.profile.product_id == offer.id
        assert result.profile.city == "Toronto"
        assert result.profile.trade_keys == ["painters"]
        assert result.profile.customer_kind.value == "residential"
        assert result.profile.signal_keys == ["website_unavailable"]
        assert result.profile.exclusion_keys == ["franchises"]
        assert result.profile.batch_size == 25
        assert result.profile.refill_policy.value == "when_depleted"
        assert result.job.status.value == "queued"
        assert result.job.payload["territory_id"] == result.profile.id
        assert session.scalar(select(func.count()).select_from(CampaignModel)) == 0
        assert (
            session.scalar(select(func.count()).select_from(TerritoryDeliveryModel))
            == 0
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
            ),
            session,
            auth,
        )

        scoring = current_profile_batch(result.profile.id, session, auth)
        assert scoring.state.value == "scoring"
        assert scoring.failure_class is None

        job = session.get(QueueJobModel, result.job.id)
        assert job is not None
        job.attempts = 1
        job.last_error = "HTTP 429 rate_limit_exceeded"
        session.commit()
        retrying = current_profile_batch(result.profile.id, session, auth)
        assert retrying.state.value == "retrying"
        assert retrying.failure_class == "rate_limit"
        assert retrying.retry_at == job.run_after

        job.status = "failed"
        session.commit()
        failed = current_profile_batch(result.profile.id, session, auth)
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


def test_profile_signals_rank_without_becoming_contact_requirements() -> None:
    _, contract = _territory_contract(
        SimpleNamespace(
            search_contract={},
            signal_keys=["website unavailable", "no quote flow"],
            exclusion_keys=["closed business", "chains"],
        )
    )

    assert {predicate.key for predicate in contract.ranking} == {
        "website_status",
        "quote_or_booking_form_present",
    }
    assert [predicate.key for predicate in contract.all_of] == ["business_operational"]
    assert contract.semantic_exclusions == ("Business is a chain or national brand",)
    assert contract.contact_requirements == ()


def test_profile_signal_threshold_and_agency_exclusion_match_saved_keys() -> None:
    _, contract = _territory_contract(
        SimpleNamespace(
            search_contract={},
            signal_keys=["reviews_under_15"],
            exclusion_keys=["agencies"],
        )
    )

    assert contract.ranking[0].key == "google_review_count"
    assert contract.ranking[0].value == 15.0
    assert contract.semantic_exclusions == (
        "Business is a marketing or web agency",
    )


def test_multi_trade_rows_are_interleaved_and_deduplicated() -> None:
    def row(business_id: str) -> dict:
        return {
            "title": business_id,
            "url": None,
            "raw": {"canonical_business_id": business_id},
        }

    merged = _merge_niche_rows(
        [[row("paint-1"), row("shared"), row("paint-2")], [row("hvac-1"), row("shared")]],
        limit=5,
    )

    assert [item["title"] for item in merged] == [
        "paint-1",
        "hvac-1",
        "shared",
        "paint-2",
    ]


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


def test_monthly_profile_schedules_next_batch_from_delivery_time() -> None:
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
                refill_policy=TerritoryRefillPolicy.MONTHLY,
                confirmed=True,
            )
        )
        scheduled = datetime(2026, 9, 28, 15, 30, tzinfo=timezone.utc)

        TerritoryRefreshService(
            session=session,
            campaigns=_FakeCampaigns(session, workspace_id="workspace:first"),
            workspace_id="workspace:first",
        ).refresh(territory.id, scheduled_for=scheduled)

        assert territory.next_run_at == datetime(2026, 10, 28, 15, 30, tzinfo=timezone.utc)


def test_delivery_requires_opportunity_but_not_contact_readiness() -> None:
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
        refresh = TerritoryRefreshService(
            session=session,
            campaigns=_FakeCampaigns(session, workspace_id="workspace:first"),
            workspace_id="workspace:first",
        )
        delivery = refresh.refresh(territory.id)
        leads = list(
            session.scalars(
                select(LeadModel)
                .where(LeadModel.campaign_id == delivery.campaign_id)
                .order_by(LeadModel.created_at)
            )
        )
        leads[0].raw_sources = [
            {"digital_opportunity": {"version": 1, "score": 15, "level": "low"}},
            {"phone": "416-555-0101"},
        ]
        leads[1].contact_email = None
        leads[1].raw_sources = [
            {"digital_opportunity": {"version": 1, "score": 55, "level": "high"}}
        ]
        session.commit()

        contacts = refresh.contacts(delivery, min_fit=territory.min_fit)
        assert [contact.id for contact in contacts] == [leads[1].id]
        assert contacts[0].contact_email is None


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
        delivery = TerritoryRefreshService(
            session=session,
            campaigns=_FakeCampaigns(session, workspace_id="workspace:first"),
            workspace_id="workspace:first",
        ).refresh(territory.id)
        first_lead = session.scalar(
            select(LeadModel).where(LeadModel.campaign_id == delivery.campaign_id).limit(1)
        )
        assert first_lead is not None
        first_lead.review_status = "not_fit"
        session.commit()

        assert enqueue_refill_if_depleted(session, territory.id) is True
        assert enqueue_refill_if_depleted(session, territory.id) is True

        jobs = list(session.scalars(select(QueueJobModel)))
        assert len(jobs) == 1
        assert jobs[0].payload["territory_id"] == territory.id


def test_failed_refresh_reuses_delivery_on_retry() -> None:
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


def test_profile_refresh_materializes_without_calling_an_llm() -> None:
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
                exclude=["chains", "franchises"],
                limit=25,
            )
        )
        refresh = TerritoryRefreshService(
            session=session,
            campaigns=_FakeCampaigns(session, workspace_id="workspace:first"),
            workspace_id="workspace:first",
        )
        delivery = refresh.refresh(profile.id)

        assert delivery.status == "ready"
        assert delivery.new_contact_count == 2
        items = list(
            session.scalars(
                select(ProfileDeliveryItemModel).where(
                    ProfileDeliveryItemModel.profile_id == profile.id
                )
            )
        )
        assert len(items) == 2

        next_delivery = refresh.refresh(
            profile.id,
            scheduled_for=datetime(2026, 10, 6, tzinfo=timezone.utc),
        )
        assert next_delivery.status == "empty"
        assert next_delivery.new_contact_count == 0
        current = current_profile_batch(
            profile.id,
            session,
            SimpleNamespace(workspace_id="workspace:first"),
        )
        assert current.state.value == "empty"


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


def test_profile_signals_rank_known_matches_without_rejecting_null_facts() -> None:
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

        assert [row["title"] for row in rows] == [
            businesses[1].display_name,
            businesses[0].display_name,
        ]
        assert rows[0]["raw"]["profile_match"]["signals"]["no_quote_flow"]["matched"] is True
        assert rows[1]["raw"]["profile_match"]["signals"]["no_quote_flow"]["value"] is None


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
            territory_id=territory.id,
            rows=[
                {"raw": {"canonical_business_id": lead.business_id}, "title": "Delivered"},
                {"raw": {"canonical_business_id": "business:new"}, "title": "New"},
            ],
        )
        assert [row["title"] for row in rows] == ["New"]


def test_business_delivered_to_one_profile_remains_available_to_another() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        offer = _offer(session, workspace_id="workspace:first")
        niche = _niche(session, slug="home_service_hvac", label="HVAC contractors")
        first_territory = TerritoryService(
            session, workspace_id="workspace:first"
        ).create(
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
        second_territory = TerritoryService(
            session, workspace_id="workspace:first"
        ).create(
            TerritoryCreate(
                product_id=offer.id,
                niche_id=niche.id,
                niche_slug=niche.slug,
                niche_label=niche.label,
                market_key="Mississauga",
                label="Mississauga HVAC",
                confirmed=True,
            )
        )
        campaigns = CampaignRepository(session, workspace_id="workspace:first")
        first_campaign = campaigns.create(
            CampaignCreate(
                product_id=offer.id,
                territory_id=first_territory.id,
                name="First profile batch",
                max_leads=2,
            )
        )
        lead = LeadRepository(session, workspace_id="workspace:first").create_from_seed(
            first_campaign.id,
            offer.id,
            LeadSeedInput(
                company_name="Shared HVAC",
                website_url="https://shared.example",
                geography="Greater Toronto Area",
            ),
        )
        second_campaign = campaigns.create(
            CampaignCreate(
                product_id=offer.id,
                territory_id=second_territory.id,
                name="Second profile batch",
                max_leads=2,
            )
        )

        rows = exclude_previously_delivered_rows(
            session,
            campaign_id=second_campaign.id,
            territory_id=second_territory.id,
            rows=[
                {
                    "raw": {"canonical_business_id": lead.business_id},
                    "title": "Shared HVAC",
                }
            ],
        )

        assert [row["title"] for row in rows] == ["Shared HVAC"]


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

    def materialize_profile_matches(self, campaign_id: str, rows: list[dict]):
        self.run_count += 1
        if self.fail_first and self.run_count == 1:
            raise RuntimeError("temporary source failure")
        campaign = self.repository.get(campaign_id)
        created = []
        for index, row in enumerate(rows, start=1):
            lead = self.leads.create_from_existing_match(
                campaign.id,
                campaign.product_id,
                row,
            )
            self.leads.attach_qualification(
                lead.id,
                QualificationResult(
                    qualified=True,
                    fit_status=(
                        AgentFitStatus.GOOD_FIT
                        if index == 1
                        else AgentFitStatus.MAYBE
                    ),
                    score=80,
                    rationale="Matches the niche.",
                    recommended_next_step="Review contact.",
                ),
            )
            created.append(lead)
        return created


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
    session.commit()
