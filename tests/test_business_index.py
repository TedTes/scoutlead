from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agent_runs.service import AgentRunService
from business_index.refresh import (
    BusinessIndexRefreshService,
    _audit_candidate_priority,
    _canonical_contact_email,
    _canonical_website_url,
    _observation_has_website,
    _round_robin_unique,
)
from business_index.pipeline import BusinessIndexPipelineService
from business_index.repository import BusinessIndexRepository
from business_index.scheduler import enqueue_due_business_index_refreshes
from campaigns.service import CampaignService
from campaigns.schemas import CampaignRead
from db.models import (
    NicheModel,
    QueueJobModel,
    RunPipelineEventModel,
    SourceItemDecisionModel,
    SourceItemModel,
)
from db.session import create_database
from job_queue.repository import QueueRepository
from job_queue.schemas import JobType
from products.repository import ProductRepository
from leads.repository import LeadRepository
from leads.schemas import LeadRead
from run_diagnostics.service import build_run_diagnostics
from seeding.service import BusinessSeedService
from source_requests.schemas import SourceRequestCreate
from source_requests.service import SourceRequestService
from territories.opportunity_audit import BusinessOpportunityAuditor
from tests.test_business_seeding import painting_seed
from tests.test_smoke_campaign import FakeWorkflowLLM
from tests.test_source_requests import FakeEmbeddingClient, _product
from tools.base import ToolResult, ToolSlot
from tools.browser import DirectHttpBrowserTool
from tools.search import SearchTool


class RecordingSourceRegistry:
    def __init__(self) -> None:
        self.calls = []

    def run(self, source, context):
        self.calls.append(source)
        suffix = len(self.calls)
        return ToolResult(
            provider=source.provider_id,
            slot=ToolSlot.DISCOVERY,
            confidence=80,
            data=[
                {
                    "title": f"Independent Painter {suffix}",
                    "url": None,
                    "snippet": "Independent residential painting contractor",
                    "geography": "Toronto, ON",
                    "contact_email": None,
                    "source": source.provider_id,
                    "raw": {
                        "id": f"{source.provider_id}-{suffix}",
                        "businessStatus": "OPERATIONAL",
                        "nationalPhoneNumber": f"41655500{suffix:02d}",
                        "googleMapsUri": f"https://maps.example/{suffix}",
                    },
                }
            ],
        )


class EmptySourceRegistry:
    def run(self, source, context):
        return ToolResult(
            provider=source.provider_id,
            slot=ToolSlot.DISCOVERY,
            confidence=80,
            data=[],
        )


def test_refresh_candidate_order_interleaves_providers_before_existing_inventory() -> None:
    assert _round_robin_unique(
        [["google-1", "google-2", "shared"], ["osm-1", "shared", "osm-2"]],
        ["existing-1", "google-1"],
    ) == [
        "google-1",
        "osm-1",
        "google-2",
        "shared",
        "osm-2",
        "existing-1",
    ]


def test_only_structured_business_sources_set_canonical_website() -> None:
    assert (
        _canonical_website_url(
            "https://official-painter.example",
            provider_id="google_places",
        )
        == "https://official-painter.example"
    )
    assert (
        _canonical_website_url(
            "https://search.example/unrelated-result",
            provider_id="configured_search",
        )
        is None
    )


def test_only_structured_business_sources_set_canonical_contact_email() -> None:
    assert (
        _canonical_contact_email(
            "owner@official-painter.example",
            provider_id="openstreetmap",
        )
        == "owner@official-painter.example"
    )
    assert (
        _canonical_contact_email(
            "directory@example.test",
            provider_id="configured_search",
        )
        is None
    )


def test_google_observation_finds_website_in_nested_provider_payload() -> None:
    assert _observation_has_website(
        {
            "provider_id": "google_places",
            "provider_payload": {
                "raw": {
                    "websiteUri": "https://www.prestigepaintinggta.ca/",
                }
            },
        }
    )


def test_audit_prioritizes_google_website_conflicts_for_repair() -> None:
    context = {
        "google_missing_ids": {"conflict", "new-missing"},
        "conflicting_website_ids": {"conflict"},
        "audited_ids": {"conflict"},
    }

    conflict = _audit_candidate_priority(
        "conflict",
        **context,
        has_website=True,
        position=2,
    )
    new_missing = _audit_candidate_priority(
        "new-missing",
        **context,
        has_website=False,
        position=1,
    )
    ordinary = _audit_candidate_priority(
        "ordinary",
        **context,
        has_website=False,
        position=0,
    )

    assert conflict < new_missing < ordinary


def test_scheduled_refresh_runs_every_provider_and_populates_the_shared_index() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(_product())
        campaigns = CampaignService(
            session=session,
            llm=FakeWorkflowLLM(),
            search_tool=SearchTool(),
            browser=DirectHttpBrowserTool(timeout_seconds=0.1),
            embedding=FakeEmbeddingClient(),
        )
        request_service = SourceRequestService(
            products=ProductRepository(session),
            campaigns=campaigns,
            agent_runs=AgentRunService(session),
            llm=FakeWorkflowLLM(),
            google_places_configured=True,
            search_configured=True,
            openstreetmap_enabled=True,
        )
        created = request_service.create(
            SourceRequestCreate(
                product_id=product.id,
                source="auto",
                prompt="Independent painters in Toronto without a website",
                max_results=5,
            )
        )
        segment_id = created.run.source_inputs["business_index_segment_id"]
        segment = BusinessIndexRepository(session).get(segment_id)
        assert segment is not None
        session.add(
            NicheModel(
                id="niche_ambiguous_painters",
                slug="ambiguous_painters",
                label=segment.niche.label,
                category=segment.niche.category,
                default_query=segment.niche.default_query,
                active=True,
                signal_vocabulary=[],
            )
        )
        session.commit()
        scheduled_before_refresh = enqueue_due_business_index_refreshes(session)
        jobs_before_refresh = session.query(QueueJobModel).count()
        registry = RecordingSourceRegistry()

        summary = BusinessIndexRefreshService(
            session=session,
            registry=registry,
            campaigns=campaigns,
            auditor=BusinessOpportunityAuditor(
                session=session,
                verifier=None,
                search=SearchTool(),
                timeout_seconds=0.1,
            ),
            embedding=FakeEmbeddingClient(),
        ).refresh(segment_id)

        next_search = request_service.create(
            SourceRequestCreate(
                product_id=product.id,
                source="auto",
                prompt="Independent painters in Toronto without a website",
                max_results=5,
            )
        )

        refreshed_run = campaigns.get(created.run.id)
        leads = LeadRepository(session).list_by_campaign(next_search.run.id)
        segment = BusinessIndexRepository(session).get(segment_id)
        job = session.query(QueueJobModel).one()
        scheduled = enqueue_due_business_index_refreshes(session)
        queued_job_count = session.query(QueueJobModel).count()
        diagnostics = build_run_diagnostics(
            session,
            run=CampaignRead.model_validate(refreshed_run),
            final_results=[],
        )
        source_items = session.query(SourceItemModel).all()
        source_item_decisions = session.query(SourceItemDecisionModel).all()

    assert [call.provider_id for call in registry.calls] == [
        "google_places",
        "openstreetmap",
        "configured_search",
    ]
    assert all(call.config["limit"] == 25 for call in registry.calls)
    assert summary["successful_source_count"] == 3
    assert summary["filled_campaign_count"] == 0
    assert refreshed_run.status == "completed"
    assert len(leads) == 2
    assert segment is not None
    assert len(segment.source_state) == 3
    assert job.type == "business_index.refresh"
    assert scheduled_before_refresh == 1
    assert jobs_before_refresh == 1
    assert scheduled == 0
    assert queued_job_count == 1
    assert diagnostics.retention == "exact"
    assert diagnostics.summary["final"] == 0
    assert len(source_items) == 3
    assert sorted(item.state for item in source_items) == [
        "audit_pending",
        "audit_pending",
        "rejected",
    ]
    assert len(source_item_decisions) == 5


def test_staged_refresh_processes_fetch_identity_audit_and_eligibility_jobs() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(_product())
        campaigns = CampaignService(
            session=session,
            llm=FakeWorkflowLLM(),
            search_tool=SearchTool(),
            browser=DirectHttpBrowserTool(timeout_seconds=0.1),
            embedding=FakeEmbeddingClient(),
        )
        created = SourceRequestService(
            products=ProductRepository(session),
            campaigns=campaigns,
            google_places_configured=True,
            search_configured=True,
            openstreetmap_enabled=True,
        ).create(
            SourceRequestCreate(
                product_id=product.id,
                source="auto",
                prompt="Independent painters in Toronto without a website",
                max_results=5,
            )
        )
        segment_id = created.run.source_inputs["business_index_segment_id"]
        pipeline = BusinessIndexPipelineService(
            session=session,
            registry=RecordingSourceRegistry(),
            campaigns=campaigns,
            auditor=BusinessOpportunityAuditor(
                session=session,
                verifier=None,
                search=SearchTool(),
                timeout_seconds=0.1,
            ),
            embedding=FakeEmbeddingClient(),
        )

        planned = pipeline.plan_refresh(segment_id)
        processed_types = []
        queue = QueueRepository(session)
        for _ in range(30):
            job = queue.claim_next()
            if job is None:
                break
            processed_types.append(job.type)
            if job.type == JobType.SOURCE_FETCH.value:
                pipeline.fetch_source(
                    segment_id,
                    source_index=int(job.payload["source_index"]),
                    task_data=job.payload["task"],
                    job_id=job.id,
                )
            elif job.type == JobType.SOURCE_ITEM_CLASSIFY.value:
                pipeline.classify_source_item(job.payload["source_item_id"], job_id=job.id)
            elif job.type == JobType.BUSINESS_IDENTITY_RESOLVE.value:
                pipeline.resolve_identity(job.payload["source_item_id"])
            elif job.type == JobType.BUSINESS_OPPORTUNITY_AUDIT.value:
                pipeline.audit_opportunity(
                    job.payload["source_item_id"],
                    business_id=job.payload["business_id"],
                )
            elif job.type == JobType.SEARCH_ELIGIBILITY_MATCH.value:
                pipeline.match_eligibility(segment_id, job_id=job.id)
            queue.complete(job.id)

        items = session.query(SourceItemModel).all()
        segment = BusinessIndexRepository(session).get(segment_id)

    assert planned["source_job_count"] == 3
    assert set(processed_types) == {
        JobType.SOURCE_FETCH.value,
        JobType.SOURCE_ITEM_CLASSIFY.value,
        JobType.BUSINESS_IDENTITY_RESOLVE.value,
        JobType.BUSINESS_OPPORTUNITY_AUDIT.value,
        JobType.SEARCH_ELIGIBILITY_MATCH.value,
    }
    assert sorted(item.state for item in items) == ["eligible", "eligible", "rejected"]
    assert segment is not None
    assert segment.next_refresh_at > segment.last_refresh_at


def test_refresh_audits_existing_inventory_for_the_next_database_search() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        BusinessSeedService(session).import_seeds(
            [painting_seed(website_url=None, contact_email=None)],
            batch_id="painting-toronto-v1",
        )
        product = ProductRepository(session).create(_product())
        campaigns = CampaignService(
            session=session,
            llm=FakeWorkflowLLM(),
            search_tool=SearchTool(),
            browser=DirectHttpBrowserTool(timeout_seconds=0.1),
            embedding=FakeEmbeddingClient(),
        )
        created = SourceRequestService(
            products=ProductRepository(session),
            campaigns=campaigns,
            agent_runs=AgentRunService(session),
            llm=FakeWorkflowLLM(),
            google_places_configured=False,
            search_configured=False,
            openstreetmap_enabled=True,
        ).create(
            SourceRequestCreate(
                product_id=product.id,
                source="auto",
                prompt="Independent residential painters in Toronto without a website",
                max_results=5,
            )
        )

        assert created.current_result_count == 0
        segment_id = created.run.source_inputs["business_index_segment_id"]
        BusinessIndexRefreshService(
            session=session,
            registry=EmptySourceRegistry(),
            campaigns=campaigns,
            auditor=BusinessOpportunityAuditor(
                session=session,
                verifier=None,
                search=SearchTool(),
                timeout_seconds=0.1,
            ),
            embedding=FakeEmbeddingClient(),
        ).refresh(segment_id)

        next_search = SourceRequestService(
            products=ProductRepository(session),
            campaigns=campaigns,
            agent_runs=AgentRunService(session),
            llm=FakeWorkflowLLM(),
            google_places_configured=False,
            search_configured=False,
            openstreetmap_enabled=True,
        ).create(
            SourceRequestCreate(
                product_id=product.id,
                source="auto",
                prompt="Independent residential painters in Toronto without a website",
                max_results=5,
            )
        )
        leads = LeadRepository(session).list_by_campaign(next_search.run.id)

    assert [lead.company_name for lead in leads] == ["Example Solo Painting Co."]
