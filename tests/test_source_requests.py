from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import pytest

from agent_runs.service import AgentRunService
from campaign_sources.repository import CampaignSourceRepository
from business_index.schemas import SearchContract
from campaigns.schemas import CampaignCreate
from campaigns.service import CampaignService
from canonical.repository import CanonicalRepository
from db.models import NicheModel, QueueJobModel
from job_queue.schemas import JobType
from db.session import create_database
from leads.repository import LeadRepository
from products.repository import ProductRepository
from products.schemas import (
    DiscoverySource,
    DiscoverySourceType,
    ProductCreate,
    QualificationCriterion,
)
from shared.errors import ValidationError
from source_requests.schemas import (
    GOOGLE_PLACES_PROVIDER_ID,
    SearchCriterionMode,
    SearchIntentCriterion,
    SourceRequestCreate,
    SourceRequestIntent,
)
from source_requests.intent import normalize_search_intent
from search_evaluations.schemas import (
    BusinessSearchEvaluationResult,
    SearchCriterionEvaluation,
    SearchEvaluationBatchResult,
    SearchEvaluationStatus,
)
from search_evaluations.service import SearchEvaluationService
from source_requests.service import SourceRequestService
from tests.test_smoke_campaign import FakeWorkflowLLM
from tools.browser import DirectHttpBrowserTool
from tools.search import SearchTool


def test_source_request_creates_structured_google_places_run_without_running() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(_product())
        request = SourceRequestCreate(
            product_id=product.id,
            source=GOOGLE_PLACES_PROVIDER_ID,
            prompt="List painting service contacts in Toronto ON",
            name="Painters Toronto shortlist",
            max_results=12,
            run_immediately=False,
        )

        result = SourceRequestService(
            products=ProductRepository(session),
            campaigns=CampaignService(
                session=session,
                llm=FakeWorkflowLLM(),
                search_tool=SearchTool(),
                browser=DirectHttpBrowserTool(timeout_seconds=0.1),
            ),
            agent_runs=AgentRunService(session),
            llm=FakeWorkflowLLM(),
        ).create(request)

        sources = CampaignSourceRepository(session).list_by_campaign(result.run.id)

        assert result.plan.source == GOOGLE_PLACES_PROVIDER_ID
        assert result.plan.action == "list_contacts"
        assert result.plan.query == "painting service Toronto ON"
        assert result.run.name == "Painters Toronto shortlist"
        assert result.summary is None
        assert sources[0].provider_id == "google_places"
        assert sources[0].input["source_request_prompt"] == request.prompt
        assert sources[0].input["source_request_action"] == "list_contacts"


def test_identical_new_search_reuses_saved_intent_without_another_llm_call() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(_product())
        llm = CountingIntentLLM()
        service = SourceRequestService(
            products=ProductRepository(session),
            campaigns=CampaignService(
                session=session,
                llm=llm,
                search_tool=SearchTool(),
                browser=DirectHttpBrowserTool(timeout_seconds=0.1),
            ),
            llm=llm,
        )
        request = SourceRequestCreate(
            product_id=product.id,
            source=GOOGLE_PLACES_PROVIDER_ID,
            prompt="List painting service contacts in Toronto ON",
            run_immediately=False,
        )

        first = service.create(request)
        second = service.create(request)
        rerun = service.rerun(first.run.id, run_immediately=False)

        assert llm.intent_calls == 1
        assert first.contract_hash == second.contract_hash == rerun.contract_hash
        assert first.interpreted_intent == second.interpreted_intent


def test_structured_search_bypasses_intent_llm_and_merges_product_defaults() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(
            _product().model_copy(
                update={
                    "ideal_customer_signals": ["Missing a clear quote flow"],
                    "exclusions": ["National chains"],
                }
            )
        )
        llm = CountingIntentLLM()
        intent = SourceRequestIntent(
            business_category="residential painting contractors",
            location="Toronto",
            criteria=[
                SearchIntentCriterion(
                    id="user_active",
                    description="Currently operating",
                    mode=SearchCriterionMode.REQUIRED,
                )
            ],
            contact_requirements=["phone"],
            search_query="residential painting contractors in Toronto",
            confidence=100,
            rationale="User supplied structured controls.",
        )
        result = SourceRequestService(
            products=ProductRepository(session),
            campaigns=CampaignService(
                session=session,
                llm=llm,
                search_tool=SearchTool(),
                browser=DirectHttpBrowserTool(timeout_seconds=0.1),
            ),
            llm=llm,
        ).create(
            SourceRequestCreate(
                product_id=product.id,
                source="auto",
                prompt="residential painting contractors in Toronto",
                business_category="residential painting contractors",
                geography="Toronto",
                intent_override=intent,
                run_immediately=False,
            )
        )

        saved = result.run.source_inputs

    assert llm.intent_calls == 0
    assert result.interpreted_intent is not None
    assert result.interpreted_intent.required_signals == ["Missing a clear quote flow"]
    assert [criterion.id for criterion in result.interpreted_intent.criteria] == [
        "user_active",
        "product_exclusion_1",
    ]
    assert saved["apply_product_defaults"] is True
    assert [criterion["id"] for criterion in saved["search_intent_base"]["criteria"]] == [
        "user_active"
    ]


def test_structured_search_can_disable_product_defaults() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(
            _product().model_copy(
                update={
                    "ideal_customer_signals": ["Missing a clear quote flow"],
                    "exclusions": ["National chains"],
                }
            )
        )
        llm = CountingIntentLLM()
        intent = SourceRequestIntent(
            business_category="residential painting contractors",
            location="Toronto",
            search_query="residential painting contractors in Toronto",
            confidence=100,
            rationale="User supplied structured controls.",
        )
        result = SourceRequestService(
            products=ProductRepository(session),
            campaigns=CampaignService(
                session=session,
                llm=llm,
                search_tool=SearchTool(),
                browser=DirectHttpBrowserTool(timeout_seconds=0.1),
            ),
            llm=llm,
        ).create(
            SourceRequestCreate(
                product_id=product.id,
                source="auto",
                prompt="residential painting contractors in Toronto",
                business_category="residential painting contractors",
                geography="Toronto",
                apply_product_defaults=False,
                intent_override=intent,
                run_immediately=False,
            )
        )

    assert llm.intent_calls == 0
    assert result.interpreted_intent is not None
    assert result.interpreted_intent.criteria == []
    assert result.interpreted_intent.required_signals == []
    assert result.interpreted_intent.excluded_result_types == []
    assert result.run.source_inputs["apply_product_defaults"] is False


def test_auto_source_request_expands_ranked_discovery_tasks() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(_product())
        result = SourceRequestService(
            products=ProductRepository(session),
            campaigns=CampaignService(
                session=session,
                llm=FakeWorkflowLLM(),
                search_tool=SearchTool(),
                browser=DirectHttpBrowserTool(timeout_seconds=0.1),
            ),
            agent_runs=AgentRunService(session),
            llm=FakeWorkflowLLM(),
            google_places_configured=True,
            search_configured=True,
            openstreetmap_enabled=True,
        ).create(
            SourceRequestCreate(
                product_id=product.id,
                source="auto",
                prompt="List painting service contacts in Toronto ON",
                max_results=12,
                run_immediately=False,
            )
        )

        sources = CampaignSourceRepository(session).list_by_campaign(result.run.id)

        assert result.plan.source == "auto"
        assert result.plan.source_preset_id == "dynamic-discovery"
        assert [source.provider_id for source in sources] == [
            "google_places",
            "openstreetmap",
            "configured_search",
        ]
        assert [source.priority for source in sources] == [10, 20, 25]
        assert sources[1].input["business_category"] == "painting service"
        assert sources[1].input["location"] == "Toronto ON"


def test_opportunity_source_request_preserves_requested_result_limit() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(
            _product().model_copy(
                update={
                    "product_name": "Local Service Website Growth",
                    "product_description": "Website and conversion improvements for local businesses.",
                    "problem_being_solved": "Weak websites and missing quote or booking flows.",
                    "ideal_customer_signals": ["Low review count"],
                }
            )
        )
        result = SourceRequestService(
            products=ProductRepository(session),
            campaigns=CampaignService(
                session=session,
                llm=FakeWorkflowLLM(),
                search_tool=SearchTool(),
                browser=DirectHttpBrowserTool(timeout_seconds=0.1),
            ),
            agent_runs=AgentRunService(session),
            llm=FakeWorkflowLLM(),
        ).create(
            SourceRequestCreate(
                product_id=product.id,
                source=GOOGLE_PLACES_PROVIDER_ID,
                prompt="Independent painters in Toronto",
                max_results=25,
                run_immediately=False,
            )
        )
        sources = CampaignSourceRepository(session).list_by_campaign(result.run.id)

        assert result.run.max_leads == 25
        assert result.run.source_inputs["requested_result_count"] == 25
        assert result.run.source_inputs["business_index_contract"]["result_count"] == 25
        assert result.run.source_inputs["requires_digital_opportunity"] is False
        assert result.run.source_inputs["website_policy"] == "any"
        assert result.run.source_inputs["business_index_contract"]["opportunity_type"] == "any"
        assert result.run.source_inputs["search_queries"] == ["painting service Toronto ON"]
        assert sources[0].input["website_policy"] == "any"
        assert sources[0].config["search_queries"] == result.run.source_inputs["search_queries"]


def test_explicit_no_website_request_uses_strict_missing_policy() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(
            _product().model_copy(
                update={
                    "product_name": "Local Service Website Growth",
                    "problem_being_solved": "Weak websites and missing quote flows.",
                }
            )
        )
        result = SourceRequestService(
            products=ProductRepository(session),
            campaigns=CampaignService(
                session=session,
                llm=FakeWorkflowLLM(),
                search_tool=SearchTool(),
                browser=DirectHttpBrowserTool(timeout_seconds=0.1),
            ),
            agent_runs=AgentRunService(session),
            llm=FakeWorkflowLLM(),
        ).create(
            SourceRequestCreate(
                product_id=product.id,
                source=GOOGLE_PLACES_PROVIDER_ID,
                prompt="Independent painters in Toronto with no website listed",
                max_results=25,
                run_immediately=False,
            )
        )

        assert result.run.source_inputs["website_policy"] == "missing"


def test_explicit_present_website_request_overrides_product_opportunity_default() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(
            _product().model_copy(
                update={
                    "product_name": "Local Service Website Growth",
                    "problem_being_solved": "Weak websites and missing quote flows.",
                }
            )
        )
        result = SourceRequestService(
            products=ProductRepository(session),
            campaigns=CampaignService(
                session=session,
                llm=FakeWorkflowLLM(),
                search_tool=SearchTool(),
                browser=DirectHttpBrowserTool(timeout_seconds=0.1),
            ),
            agent_runs=AgentRunService(session),
            llm=FakeWorkflowLLM(),
        ).create(
            SourceRequestCreate(
                product_id=product.id,
                source=GOOGLE_PLACES_PROVIDER_ID,
                prompt="Independent painters in Toronto with website",
                max_results=25,
                run_immediately=False,
            )
        )

        contract = result.run.source_inputs["business_index_contract"]
        assert result.run.source_inputs["website_policy"] == "any"
        assert contract["opportunity_type"] == "any"
        assert contract["search_contract"]["all_of"] == [
            {
                "key": "website_status",
                "operator": "equals",
                "value": "present",
            }
        ]
        assert contract["search_contract"]["any_of"] == []


def test_search_intent_keeps_scope_out_of_criteria_and_website_out_of_contacts() -> None:
    normalized = normalize_search_intent(
        SourceRequestIntent(
            business_category="residential painting contractors",
            location="Toronto",
            criteria=[
                SearchIntentCriterion(
                    id="category",
                    description="Business is a residential painting contractor",
                    mode=SearchCriterionMode.REQUIRED,
                ),
                SearchIntentCriterion(
                    id="location",
                    description="Business is located in Toronto",
                    mode=SearchCriterionMode.REQUIRED,
                ),
                SearchIntentCriterion(
                    id="website",
                    description="Has a public website",
                    mode=SearchCriterionMode.REQUIRED,
                    fact_key="website_status",
                    operator="equals",
                    value="present",
                ),
            ],
            contact_requirements=["website"],
            search_query="residential painting contractors in Toronto",
            confidence=90,
            rationale="Parsed request",
        )
    )

    assert [criterion.id for criterion in normalized.criteria] == ["website"]
    assert normalized.contact_requirements == []


def test_search_intent_inherits_product_geography_when_request_omits_it() -> None:
    normalized = normalize_search_intent(
        SourceRequestIntent(
            business_category="residential painting contractors",
            location="",
            search_query="residential painting contractors",
            confidence=90,
            rationale="Parsed request",
        ),
        default_geography="Canada",
    )

    assert normalized.location == "Canada"
    assert normalized.search_query == "residential painting contractors in Canada"


def test_dynamic_website_search_returns_existing_business_without_semantic_gate() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        session.add(
            NicheModel(
                id="niche_residential_painters",
                slug="residential_painting_contractors",
                label="Residential painting contractors",
                category="residential painting contractors",
                default_query="residential painting contractors",
                active=True,
            )
        )
        session.commit()
        product = ProductRepository(session).create(_product())
        CanonicalRepository(session).upsert_from_discovery_result(
            company_name="Current Website Painter",
            website_url="https://current-painter.example",
            geography="Toronto",
            description="Independent residential painting contractor",
            source="google_places",
            raw={
                "id": "places/current-painter",
                "websiteUri": "https://current-painter.example",
                "source_request_intent": {
                    "business_category": "residential painting contractors",
                    "location": "Toronto",
                },
            },
        )
        llm = ScopeDuplicatingIntentLLM()
        service = SourceRequestService(
            products=ProductRepository(session),
            campaigns=CampaignService(
                session=session,
                llm=llm,
                search_tool=SearchTool(),
                browser=DirectHttpBrowserTool(timeout_seconds=0.1),
            ),
            llm=llm,
        )

        result = service.create(
            SourceRequestCreate(
                product_id=product.id,
                prompt="Independent residential painting contractors in Toronto with website",
                max_results=25,
            )
        )

        assert result.state == "ready"
        assert result.run.status == "completed"
        assert result.current_result_count == 1
        assert [
            lead.company_name
            for lead in LeadRepository(session).list_by_campaign(result.run.id)
        ] == ["Current Website Painter"]
        assert session.query(QueueJobModel).count() == 0


def test_semantic_candidates_stay_on_run_until_batch_evaluation_finishes() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        session.add(
            NicheModel(
                id="niche_residential_painters",
                slug="residential_painting_contractors",
                label="Residential painting contractors",
                category="residential painting contractors",
                default_query="residential painting contractors",
                active=True,
            )
        )
        session.commit()
        product = ProductRepository(session).create(_product())
        business = CanonicalRepository(session).upsert_from_discovery_result(
            company_name="Independent Painter",
            geography="Toronto",
            description="Owner-operated residential painting contractor",
            source="google_places",
            raw={
                "id": "places/independent-painter",
                "nationalPhoneNumber": "416-555-0101",
                "source_request_intent": {
                    "business_category": "residential painting contractors",
                    "location": "Toronto",
                },
            },
        )
        llm = SemanticIntentAndBatchLLM()
        campaigns = CampaignService(
            session=session,
            llm=llm,
            search_tool=SearchTool(),
            browser=DirectHttpBrowserTool(timeout_seconds=0.1),
        )
        service = SourceRequestService(
            products=ProductRepository(session),
            campaigns=campaigns,
            llm=llm,
        )
        created = service.create(
            SourceRequestCreate(
                product_id=product.id,
                prompt="Independent residential painting contractors in Toronto",
                max_results=25,
            )
        )

        queued = session.query(QueueJobModel).one()
        leads = LeadRepository(session).list_by_campaign(created.run.id)
        assert created.state == "expanding"
        assert created.run.status == "expanding"
        assert queued.type == JobType.BUSINESS_SEARCH_EVALUATE_BATCH.value
        assert [lead.business_id for lead in leads] == [business.business_id]
        assert leads[0].status == "researching"

        SearchEvaluationService(session=session, llm=llm).evaluate_batch(
            business_ids=queued.payload["business_ids"],
            contract_hash=queued.payload["contract_hash"],
            contract=SearchContract.from_dict(queued.payload["contract"]),
            evidence_fresh_after=None,
        )
        completed = service.finalize_search_evaluations(created.run.id)

        assert completed.status == "completed"
        assert campaigns.results(created.run.id)[0].company_name == "Independent Painter"


def test_source_request_rerun_clones_saved_prompt_and_source_without_running() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(_product())
        service = SourceRequestService(
            products=ProductRepository(session),
            campaigns=CampaignService(
                session=session,
                llm=FakeWorkflowLLM(),
                search_tool=SearchTool(),
                browser=DirectHttpBrowserTool(timeout_seconds=0.1),
            ),
            agent_runs=AgentRunService(session),
            llm=FakeWorkflowLLM(),
        )
        first = service.create(
            SourceRequestCreate(
                product_id=product.id,
                source=GOOGLE_PLACES_PROVIDER_ID,
                prompt="List painting service contacts in Toronto ON",
                name="Painters Toronto shortlist",
                max_results=12,
                run_immediately=False,
            )
        )

        rerun = service.rerun(first.run.id, run_immediately=False)
        rerun_sources = CampaignSourceRepository(session).list_by_campaign(rerun.run.id)

        assert rerun.run.id != first.run.id
        assert rerun.run.name == "Painters Toronto shortlist 1"
        assert rerun_sources[0].provider_id == GOOGLE_PLACES_PROVIDER_ID
        assert rerun_sources[0].input["source_request_source"] == GOOGLE_PLACES_PROVIDER_ID
        assert rerun_sources[0].input["source_request_prompt"] == "List painting service contacts in Toronto ON"
        assert rerun.run.max_leads == 12


def test_source_request_creates_configured_apify_run_without_running() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(_product())

        result = SourceRequestService(
            products=ProductRepository(session),
            campaigns=CampaignService(
                session=session,
                llm=FakeWorkflowLLM(),
                search_tool=SearchTool(),
                browser=DirectHttpBrowserTool(timeout_seconds=0.1),
            ),
            agent_runs=AgentRunService(session),
            llm=FakeWorkflowLLM(),
            apify_sources=[
                {
                    "id": "classifieds",
                    "label": "Classifieds",
                    "input_template": {
                        "searchQueries": ["{{query}}"],
                        "maxResults": "{{limit}}",
                    },
                }
            ],
        ).create(
            SourceRequestCreate(
                product_id=product.id,
                source="classifieds",
                prompt="List painting service contacts in Toronto ON",
                max_results=7,
                run_immediately=False,
            )
        )

        sources = CampaignSourceRepository(session).list_by_campaign(result.run.id)

        assert result.plan.source == "classifieds"
        assert result.plan.source_preset_id == "apify-actor-source"
        assert result.plan.query == "painting service in Toronto ON"
        assert sources[0].provider_id == "classifieds"
        assert sources[0].input["source_request_source"] == "classifieds"
        assert sources[0].config["actor_input"] == {
            "searchQueries": ["painting service in Toronto ON"],
            "maxResults": 7,
        }


def test_source_request_accepts_multiple_apify_sources() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(_product())

        result = SourceRequestService(
            products=ProductRepository(session),
            campaigns=CampaignService(
                session=session,
                llm=FakeWorkflowLLM(),
                search_tool=SearchTool(),
                browser=DirectHttpBrowserTool(timeout_seconds=0.1),
            ),
            agent_runs=AgentRunService(session),
            llm=FakeWorkflowLLM(),
            apify_sources=[
                {
                    "id": "kijiji",
                    "label": "Kijiji",
                    "input_template": {"query": "{{query}}", "maxResults": "{{limit}}"},
                },
                {
                    "id": "homestars",
                    "label": "HomeStars",
                    "input_template": {"query": "{{query}}", "maxResults": "{{limit}}"},
                },
            ],
        ).create(
            SourceRequestCreate(
                product_id=product.id,
                source="homestars",
                prompt="List painting service contacts in Toronto ON",
                max_results=6,
                run_immediately=False,
            )
        )

        sources = CampaignSourceRepository(session).list_by_campaign(result.run.id)

        assert result.plan.source == "homestars"
        assert "HomeStars" in result.plan.explanation
        assert sources[0].provider_id == "homestars"
        assert sources[0].input["source_selection"] == "homestars"


def test_source_request_rejects_unconfigured_source_adapter() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(_product())

        with pytest.raises(ValidationError):
            SourceRequestService(
                products=ProductRepository(session),
                campaigns=CampaignService(
                    session=session,
                    llm=FakeWorkflowLLM(),
                    search_tool=SearchTool(),
                    browser=DirectHttpBrowserTool(timeout_seconds=0.1),
                ),
                agent_runs=AgentRunService(session),
                llm=FakeWorkflowLLM(),
                apify_source_provider_id="configured_apify",
            ).plan(
                SourceRequestCreate(
                    product_id=product.id,
                    source="unknown_source",
                    prompt="List painting service contacts in Toronto ON",
                )
            )


def test_broad_source_request_returns_existing_category_and_market_match() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        session.add(
            NicheModel(
                id="niche_painting",
                slug="home_service_painting",
                label="Home Service Painting",
                category="home service painting",
                default_query="painting service contacts",
                active=True,
            )
        )
        session.commit()
        product = ProductRepository(session).create(_product())
        CanonicalRepository(session, embedding=FakeEmbeddingClient()).upsert_from_discovery_result(
            company_name="All Painting Toronto",
            website_url="https://allpainting.ca",
            contact_email="info@allpainting.ca",
            geography="Toronto, ON",
            description="Professional painting company offering residential painting and free quotes.",
            source="google_places",
            raw={
                "id": "places/all-painting",
                "query": "painting service Toronto ON",
                "nationalPhoneNumber": "(416) 710-4224",
                "source_request_intent": {
                    "business_category": "painting service",
                    "location": "Toronto ON",
                    "country": "Canada",
                    "required_signals": ["contact details"],
                    "search_query": "painting service Toronto ON",
                },
                "website_enrichment": {
                    "quote_signals": ["free quote"],
                    "service_signals": ["residential painting"],
                    "has_contact_form": True,
                    "has_quote_form": True,
                },
                "digital_opportunity": {
                    "version": 1,
                    "score": 30,
                    "level": "moderate",
                    "assessed_at": "2026-10-01T12:00:00+00:00",
                    "signals": [
                        {
                            "key": "missing_quote_or_booking_form",
                            "message": "No quote form found.",
                            "points": 30,
                        }
                    ],
                },
            },
        )
        search_tool = CountingSearchTool()
        result = SourceRequestService(
            products=ProductRepository(session),
            campaigns=CampaignService(
                session=session,
                llm=FakeWorkflowLLM(),
                search_tool=search_tool,
                browser=DirectHttpBrowserTool(timeout_seconds=0.1),
                embedding=FakeEmbeddingClient(),
                semantic_cache_min_score=0.2,
                semantic_cache_min_results=1,
            ),
            agent_runs=AgentRunService(session),
            llm=FakeWorkflowLLM(),
        ).create(
            SourceRequestCreate(
                product_id=product.id,
                source=GOOGLE_PLACES_PROVIDER_ID,
                prompt="List painting service contacts in Toronto ON",
                max_results=5,
                run_immediately=True,
            )
        )

        leads = LeadRepository(session).list_by_campaign(result.run.id)
        jobs = session.query(QueueJobModel).all()

    assert search_tool.calls == 0
    assert result.summary is None
    assert result.current_result_count == 1
    assert result.requested_result_count == 5
    assert result.state == "ready"
    assert result.run.status == "completed"
    assert jobs == []
    assert [lead.company_name for lead in leads] == ["All Painting Toronto"]


def test_contact_listing_run_does_not_create_outreach_drafts() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(_product_with_seed())
        service = CampaignService(
            session=session,
            llm=FakeWorkflowLLM(),
            search_tool=SearchTool(),
            browser=DirectHttpBrowserTool(timeout_seconds=0.1),
        )
        run = service.create(
            CampaignCreate(
                product_id=product.id,
                name="List contacts only",
                max_leads=5,
            )
        )

        summary = service.run_contact_listing(run.id)

        assert summary.drafted_message_count == 0
        assert summary.campaign.status == "completed"
        assert session.execute(text("select count(*) from messages")).scalar_one() == 0


def test_source_request_compiles_url_actor_input_from_source_template() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(_product())

        result = SourceRequestService(
            products=ProductRepository(session),
            campaigns=CampaignService(
                session=session,
                llm=FakeWorkflowLLM(),
                search_tool=SearchTool(),
                browser=DirectHttpBrowserTool(timeout_seconds=0.1),
            ),
            agent_runs=AgentRunService(session),
            llm=FakeWorkflowLLM(),
            apify_sources=[
                {
                    "id": "kijiji",
                    "label": "Kijiji",
                    "input_kind": "classified_search_url",
                    "search_url_template": (
                        "https://example.test/{{location_slug}}/{{business_slug}}"
                    ),
                    "input_template": {
                        "urls": [{"url": "{{source_url}}"}],
                        "maxRecords": "{{limit}}",
                    },
                    "result_mapping": {"url": ["listingUrl"]},
                }
            ],
        ).create(
            SourceRequestCreate(
                product_id=product.id,
                source="kijiji",
                prompt="List painting service contacts in Toronto ON",
                max_results=9,
                run_immediately=False,
            )
        )

        sources = CampaignSourceRepository(session).list_by_campaign(result.run.id)

        assert result.plan.query == "https://example.test/toronto-on/painting-service"
        assert result.plan.intent is not None
        assert result.plan.intent.business_category == "painting service"
        assert sources[0].config["actor_input"] == {
            "urls": [{"url": "https://example.test/toronto-on/painting-service"}],
            "maxRecords": 9,
        }
        assert sources[0].input["source_request_intent"]["business_category"] == "painting service"


def _product() -> ProductCreate:
    return ProductCreate(
        product_name="Quote Tool",
        product_description="A quoting tool for residential painting service providers.",
        target_customer="Residential painting service providers",
        problem_being_solved="Preparing quotes after walkthroughs is slow.",
        value_proposition="Create customer-ready quotes faster.",
        target_geography="Canada",
        validation_goal="List relevant contacts.",
        qualification_criteria=[
            QualificationCriterion(label="Residential painting service", required=True)
        ],
        preferred_discovery_sources=[],
        outreach_objective="No outreach for listing requests.",
        constraints=["Human approval required before outbound messages are sent."],
    )


class CountingSearchTool(SearchTool):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    @property
    def is_configured(self) -> bool:
        return True

    def search(self, *args, **kwargs):
        self.calls += 1
        return []


class CountingIntentLLM(FakeWorkflowLLM):
    def __init__(self) -> None:
        self.intent_calls = 0

    def generate_object(self, **kwargs):
        if kwargs["response_model"] is SourceRequestIntent:
            self.intent_calls += 1
        return super().generate_object(**kwargs)


class ScopeDuplicatingIntentLLM(FakeWorkflowLLM):
    def generate_object(self, **kwargs):
        if kwargs["response_model"] is SourceRequestIntent:
            return SourceRequestIntent(
                business_category="residential painting contractors",
                location="Toronto",
                criteria=[
                    SearchIntentCriterion(
                        id="category",
                        description="Business is a residential painting contractor",
                        mode=SearchCriterionMode.REQUIRED,
                    ),
                    SearchIntentCriterion(
                        id="location",
                        description="Business is located in Toronto",
                        mode=SearchCriterionMode.REQUIRED,
                    ),
                    SearchIntentCriterion(
                        id="website",
                        description="Has a public website",
                        mode=SearchCriterionMode.REQUIRED,
                        fact_key="website_status",
                        operator="equals",
                        value="present",
                    ),
                ],
                contact_requirements=["website"],
                search_query="residential painting contractors in Toronto",
                confidence=90,
                rationale="Parsed request",
            )
        return super().generate_object(**kwargs)


class SemanticIntentAndBatchLLM(FakeWorkflowLLM):
    def generate_object(self, **kwargs):
        response_model = kwargs["response_model"]
        if response_model is SourceRequestIntent:
            return SourceRequestIntent(
                business_category="residential painting contractors",
                location="Toronto",
                criteria=[
                    SearchIntentCriterion(
                        id="independent",
                        description="Independent owner-operated business",
                        mode=SearchCriterionMode.REQUIRED,
                    )
                ],
                search_query="residential painting contractors in Toronto",
                confidence=90,
                rationale="Parsed request",
            )
        if response_model is SearchEvaluationBatchResult:
            return SearchEvaluationBatchResult(
                results=[
                    BusinessSearchEvaluationResult(
                        business_id=business["id"],
                        status=SearchEvaluationStatus.MATCHED,
                        confidence=90,
                        rationale="Evidence describes an owner-operated business.",
                        criteria=[
                            SearchCriterionEvaluation(
                                criterion="Independent owner-operated business",
                                matched=True,
                                evidence=[business.get("description") or business["name"]],
                            )
                        ],
                    )
                    for business in kwargs["context"]["businesses"]
                ]
            )
        return super().generate_object(**kwargs)


class FakeEmbeddingClient:
    model = "fake-embedding"
    dimension = 6

    def embed_text(self, text: str) -> list[float]:
        lower = text.lower()
        return [
            sum(lower.count(term) for term in ("paint", "painter", "painting")),
            sum(lower.count(term) for term in ("toronto", "ontario", "canada")),
            sum(lower.count(term) for term in ("quote", "estimate")),
            sum(lower.count(term) for term in ("phone", "contact", "email")),
            sum(lower.count(term) for term in ("roof", "hvac", "plumb")),
            1.0,
        ]


def _product_with_seed() -> ProductCreate:
    product = _product()
    product.preferred_discovery_sources = [
        DiscoverySource(
            type=DiscoverySourceType.SEED,
            value="Cedar Painting|https://example.com|Residential painter|Toronto ON|owner@example.com",
        )
    ]
    return product
