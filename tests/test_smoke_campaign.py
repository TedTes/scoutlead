from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pytest

from campaign_sources.repository import CampaignSourceRepository
from campaigns.schemas import CampaignCreate
from campaigns.service import CampaignService
from conversations.schemas import (
    FollowUpAction,
    ResponseClassification,
    ResponseIntent,
)
from db.session import create_database
from insights.schemas import CampaignInsightDraft, Finding, IcpVerdict, IcpVerdictValue
from leads.schemas import CriterionScore, LeadResearch, QualificationResult
from messages.schemas import OutreachDraft
from products.repository import ProductRepository
from products.schemas import (
    DiscoverySource,
    DiscoverySourceType,
    ProductCreate,
    QualificationCriterion,
)
from shared.errors import ValidationError
from source_requests.schemas import (
    SearchCriterionMode,
    SearchIntentCriterion,
    SourceRequestIntent,
)
from tools.browser import DirectHttpBrowserTool
from tools.search import SearchTool


class FakeWorkflowLLM:
    def generate_object(
        self,
        *,
        task: str,
        system: str,
        prompt: str,
        response_model,
        context: dict | None = None,
    ):
        context = context or {}
        if response_model is SourceRequestIntent:
            request = context["request"]
            prompt = request["prompt"]
            lower = prompt.lower()
            location = "Toronto ON" if "Toronto" in prompt else ""
            criteria = []
            if "no website" in lower or "without a website" in lower:
                criteria.append(
                    SearchIntentCriterion(
                        id="website_missing",
                        description="Website is missing or not listed",
                        mode=SearchCriterionMode.REQUIRED,
                        fact_key="website_status",
                        operator="equals",
                        value="missing",
                        evidence_requirement="Current website-presence evidence",
                    )
                )
            elif "with website" in lower or "with a website" in lower:
                criteria.append(
                    SearchIntentCriterion(
                        id="website_present",
                        description="Business has a website",
                        mode=SearchCriterionMode.REQUIRED,
                        fact_key="website_status",
                        operator="equals",
                        value="present",
                        evidence_requirement="Current website-presence evidence",
                    )
                )
            return SourceRequestIntent(
                business_category="painting service",
                location=location,
                country="Canada",
                criteria=criteria,
                required_signals=["contact details"],
                excluded_result_types=["directories", "marketplaces"],
                search_query="painting service in Toronto ON",
                search_url="https://example.test/search/painting-service-toronto-on"
                if "url source" in prompt
                else "",
                confidence=80,
                rationale="Parsed the local business category and market from the request.",
            )
        if response_model is LeadResearch:
            lead = context["lead"]
            product = context["product"]
            return LeadResearch(
                summary=lead.get("description") or f"{lead['company_name']} appears relevant.",
                business_type=product["target_customer"],
                geography=lead.get("geography"),
                website_url=lead.get("website_url"),
                contact_email=lead.get("contact_email"),
                signals=["Matches target customer"],
                pain_indicators=["Relevant workflow signal"],
                disqualifiers=[],
                sources=["seed"],
                confidence=80,
            )
        if response_model is QualificationResult:
            product = context["product"]
            return QualificationResult(
                qualified=True,
                score=85,
                rationale="Lead matches the configured target customer.",
                criteria=[
                    CriterionScore(
                        criterion_id=criterion.get("id") or criterion["label"],
                        label=criterion["label"],
                        score=85,
                        evidence=["Seed lead matches this criterion."],
                    )
                    for criterion in product["qualification_criteria"]
                ],
                recommended_next_step="Draft outreach for human review.",
            )
        if response_model is OutreachDraft:
            lead = context["lead"]
            product = context["product"]
            return OutreachDraft(
                subject=f"{product['product_name']} question for {lead['company_name']}",
                body="Hi there,\n\nOpen to a short customer discovery conversation?\n\nThanks,",
                personalization_notes=["Referenced public seed signal."],
                approach_tag="test_validation_request",
            )
        if response_model is ResponseClassification:
            body = context.get("body", "").lower()
            if "interview" in body or "schedule" in body:
                return ResponseClassification(
                    intent=ResponseIntent.INTERVIEW_REQUEST,
                    confidence=90,
                    rationale="Response includes scheduling/interview language.",
                    suggested_reply="Share available times.",
                    follow_up_action=FollowUpAction.SCHEDULE_INTERVIEW,
                )
            return ResponseClassification(
                intent=ResponseIntent.INTERESTED,
                confidence=80,
                rationale="Response is positive.",
                suggested_reply="Reply with next steps.",
                follow_up_action=FollowUpAction.REPLY,
            )
        if response_model is CampaignInsightDraft:
            return CampaignInsightDraft(
                summary="Test campaign produced a qualified lead and response evidence.",
                findings=[
                    Finding(
                        theme="Lead fit",
                        summary="The seed lead matched the configured ICP.",
                        evidence=["Seed lead matched this criterion."],
                        count=1,
                        confidence=80,
                    )
                ],
                icp_verdict=IcpVerdict(
                    verdict=IcpVerdictValue.MIXED,
                    rationale="Small test sample with positive evidence.",
                    recommended_action="Collect more responses.",
                ),
                evidence=["Smoke test evidence"],
            )
        raise AssertionError(f"Unhandled response model {response_model}")


def test_google_places_source_preset_creates_campaign_source_row() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(
            ProductCreate(
                product_name="Painter Quote Tool",
                product_description="Quoting tool for residential painters.",
                target_customer="Residential painting companies",
                problem_being_solved="Creating professional quotes after walkthroughs is slow.",
                value_proposition="Create customer-ready quotes faster.",
                target_geography="United States",
                validation_goal="Book customer discovery interviews.",
                qualification_criteria=[
                    QualificationCriterion(label="Residential painting company", required=True)
                ],
                preferred_discovery_sources=[
                    DiscoverySource(
                        type=DiscoverySourceType.WEB_SEARCH,
                        value="residential painters",
                    )
                ],
                outreach_objective="Ask for a discovery conversation.",
                constraints=["Human approval required before sending."],
            )
        )

        campaign = CampaignService(
            session=session,
            llm=FakeWorkflowLLM(),
            search_tool=SearchTool(),
            browser=DirectHttpBrowserTool(timeout_seconds=0.1),
        ).create(
            CampaignCreate(
                product_id=product.id,
                name="Google Places source campaign",
                max_leads=10,
                source_preset_id="google-places-local-business",
                source_input="residential painters Austin TX",
            )
        )

        sources = CampaignSourceRepository(session).list_by_campaign(campaign.id)

        assert len(sources) == 1
        assert sources[0].provider_id == "google_places"
        assert sources[0].input["query"] == "residential painters Austin TX"
        assert sources[0].input["geography"] == "United States"
        assert sources[0].input["source_selection"] is None
        assert sources[0].config["region_code"] == "US"
        assert sources[0].config["include_pure_service_area_businesses"] is True


def test_explicit_source_input_without_preset_defaults_to_google_places() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(
            ProductCreate(
                product_name="Painter Quote Tool",
                product_description="Quoting tool for residential painters.",
                target_customer="Residential painting companies",
                problem_being_solved="Creating professional quotes after walkthroughs is slow.",
                value_proposition="Create customer-ready quotes faster.",
                target_geography="United States",
                validation_goal="Book customer discovery interviews.",
                qualification_criteria=[
                    QualificationCriterion(label="Residential painting company", required=True)
                ],
                preferred_discovery_sources=[],
                outreach_objective="Ask for a discovery conversation.",
                constraints=["Human approval required before sending."],
            )
        )

        campaign = CampaignService(
            session=session,
            llm=FakeWorkflowLLM(),
            search_tool=SearchTool(),
            browser=DirectHttpBrowserTool(timeout_seconds=0.1),
        ).create(
            CampaignCreate(
                product_id=product.id,
                name="Implicit places source campaign",
                max_leads=10,
                source_input="residential painters Austin TX",
            )
        )

        sources = CampaignSourceRepository(session).list_by_campaign(campaign.id)

        assert len(sources) == 1
        assert sources[0].provider_id == "google_places"
        assert sources[0].input["source_selection"] == "google_places_local_business"


def test_broad_explicit_source_input_without_preset_is_rejected() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRepository(session).create(
            ProductCreate(
                product_name="Painter Quote Tool",
                product_description="Quoting tool for residential painters.",
                target_customer="Residential painting companies",
                problem_being_solved="Creating professional quotes after walkthroughs is slow.",
                value_proposition="Create customer-ready quotes faster.",
                target_geography="United States",
                validation_goal="Book customer discovery interviews.",
                qualification_criteria=[
                    QualificationCriterion(label="Residential painting company", required=True)
                ],
                preferred_discovery_sources=[],
                outreach_objective="Ask for a discovery conversation.",
                constraints=["Human approval required before sending."],
            )
        )

        with pytest.raises(ValidationError):
            CampaignService(
                session=session,
                llm=FakeWorkflowLLM(),
                search_tool=SearchTool(),
                browser=DirectHttpBrowserTool(timeout_seconds=0.1),
            ).create(
                CampaignCreate(
                    product_id=product.id,
                    name="Broad source campaign",
                    max_leads=10,
                    source_input="solo painter OR independent painter OR field service technician",
                )
            )
