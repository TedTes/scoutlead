from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import pytest

from agent_runs.service import AgentRunService
from campaign_sources.repository import CampaignSourceRepository
from campaigns.schemas import CampaignCreate
from campaigns.service import CampaignService
from db.session import create_database
from products.repository import ProductRepository
from products.schemas import (
    DiscoverySource,
    DiscoverySourceType,
    ProductCreate,
    QualificationCriterion,
)
from shared.errors import ValidationError
from source_requests.schemas import GOOGLE_PLACES_PROVIDER_ID, SourceRequestCreate
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
        assert result.plan.query == "painting service in Toronto ON"
        assert result.run.name == "Painting Service · Toronto ON"
        assert result.summary is None
        assert sources[0].provider_id == "google_places"
        assert sources[0].input["source_request_prompt"] == request.prompt
        assert sources[0].input["source_request_action"] == "list_contacts"


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


def _product_with_seed() -> ProductCreate:
    product = _product()
    product.preferred_discovery_sources = [
        DiscoverySource(
            type=DiscoverySourceType.SEED,
            value="Cedar Painting|https://example.com|Residential painter|Toronto ON|owner@example.com",
        )
    ]
    return product
