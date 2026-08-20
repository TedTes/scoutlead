from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from campaign_sources.repository import CampaignSourceRepository
from campaign_sources.schemas import CampaignSourceCreate, CampaignSourceMode, CampaignSourceSlot
from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignCreate, CampaignRead
from db.session import create_database
from discovery.repository import DiscoveryCandidateRepository
from discovery.schemas import DiscoveryCandidateType
from leads.repository import LeadRepository
from memory.repository import MemoryRepository
from products.repository import ProductRepository
from products.schemas import DiscoverySource, DiscoverySourceType, ProductCreate, ProductRead, QualificationCriterion
from tools.search import SearchResult
from workflows.discovery import DiscoveryWorkflow


class FakeSearchTool:
    name = "search"
    is_configured = True

    def __init__(self, rows: list[SearchResult]) -> None:
        self.rows = rows

    def search(
        self,
        *,
        product: ProductRead,
        campaign: CampaignRead,
        source: DiscoverySource,
        limit: int,
        query: str | None = None,
    ) -> list[SearchResult]:
        del product, campaign, source, query
        return self.rows[:limit]


def test_discovery_stores_salary_result_as_rejected_candidate_not_lead() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        product = ProductRead.model_validate(ProductRepository(session).create(product_input()))
        campaign = CampaignRead.model_validate(
            CampaignRepository(session).create(
                CampaignCreate(
                    product_id=product.id,
                    name="Candidate gate test",
                    max_leads=5,
                )
            )
        )
        CampaignSourceRepository(session).create_many(
            [
                CampaignSourceCreate(
                    campaign_id=campaign.id,
                    slot=CampaignSourceSlot.DISCOVERY,
                    provider_id="configured_search",
                    mode=CampaignSourceMode.ACCUMULATE,
                    input={"query": '"residential painting company"', "source_type": "web_search"},
                    config={"limit": 5},
                )
            ]
        )

        workflow = DiscoveryWorkflow(
            campaigns=CampaignRepository(session),
            campaign_sources=CampaignSourceRepository(session),
            candidates=DiscoveryCandidateRepository(session),
            leads=LeadRepository(session),
            memory=MemoryRepository(session),
            search_tool=FakeSearchTool(
                [
                    SearchResult(
                        title="Painter Salary in the United States (2026) - ERI SalaryExpert",
                        url="https://www.salaryexpert.com/salary/job/painter/united-states",
                        snippet="Average painter salary and compensation data in the United States.",
                        source="tavily",
                    ),
                    SearchResult(
                        title="Cedar & Sons Painting",
                        url="https://cedarpaint.example",
                        snippet="Residential painting company offering free estimates. Contact us for a quote.",
                        geography="Austin, TX",
                        source="tavily",
                    ),
                ]
            ),
        )

        leads = workflow.run(product, campaign)
        candidates = DiscoveryCandidateRepository(session).list_by_campaign(campaign.id)

        assert len(candidates) == 2
        assert len(leads) == 1
        salary = next(candidate for candidate in candidates if "Salary" in candidate.title)
        business = next(candidate for candidate in candidates if candidate.title == "Cedar & Sons Painting")
        assert salary.candidate_type == DiscoveryCandidateType.SALARY.value
        assert salary.rejection_reason == "Salary or compensation page, not a customer business."
        assert salary.lead_id is None
        assert business.candidate_type == DiscoveryCandidateType.TARGET_BUSINESS.value
        assert business.lead_id == leads[0].id


def product_input() -> ProductCreate:
    return ProductCreate(
        product_name="QuoteVan",
        product_description="Mobile quoting app for residential painters.",
        target_customer="Residential painting companies in the United States",
        problem_being_solved="Painters need to create professional job quotes after walkthroughs.",
        value_proposition="Create customer-ready quotes faster.",
        target_geography="United States",
        validation_goal="Book discovery interviews.",
        qualification_criteria=[
            QualificationCriterion(
                id="painting_company",
                label="Residential painting company",
                description="Provides painting services to homeowners.",
                weight=1,
                required=True,
                evidence_required=True,
            )
        ],
        preferred_discovery_sources=[
            DiscoverySource(
                type=DiscoverySourceType.WEB_SEARCH,
                value='"residential painting company" "free estimate" "contact us"',
            )
        ],
        outreach_objective="Ask for a discovery conversation.",
        constraints=["Human approval required before sending."],
        source_evidence={"created_at": datetime.now(UTC).isoformat()},
    )
