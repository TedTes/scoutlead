from datetime import UTC, datetime

from products.schemas import DiscoverySource, DiscoverySourceType, ProductRead, QualificationCriterion
from tools.search import SearchResult, SearchTool


def test_search_filter_excludes_content_pages_and_keeps_business_sites() -> None:
    rows = [
        SearchResult(
            title="Why Customers Stop Responding After You Send a Quote",
            url="https://www.youtube.com/watch?v=abc",
            snippet="Video",
        ),
        SearchResult(
            title="Configure Quotes Faster: 6 Strategies",
            url="https://www.cincom.com/blog/cpq/configure-quotes-faster",
            snippet="Blog",
        ),
        SearchResult(
            title="Best Estimating Software For Contractors 2026",
            url="https://quoteiq.example/estimating-software",
            snippet="Vendor category page",
        ),
        SearchResult(
            title="Fernwood Painting",
            url="https://fernwoodpainting.example",
            snippet="Residential painting company",
        ),
    ]

    filtered = SearchTool._filter_business_results(rows, 10)

    assert [row.title for row in filtered] == ["Fernwood Painting"]


def test_search_filter_excludes_solution_vendor_pages_for_non_software_icp() -> None:
    rows = [
        SearchResult(
            title="Quoting & Estimates | Professional Estimates In Seconds",
            url="https://quoteiq.example",
            snippet="Quotes delivered in under 60 seconds from mobile",
        ),
        SearchResult(
            title="Job Quoting Software With Online Approvals",
            url="https://orderry.example/job-quoting-software",
            snippet="Fast job quoting on desktop and mobile",
        ),
        SearchResult(
            title="Cedar & Sons Painting",
            url="https://cedar-painting.example",
            snippet="Residential painting company in Austin",
        ),
    ]

    filtered = SearchTool._filter_business_results(rows, 10, product())

    assert [row.title for row in filtered] == ["Cedar & Sons Painting"]


def test_search_query_uses_configured_source_without_hidden_expansion() -> None:
    source = DiscoverySource(
        type=DiscoverySourceType.WEB_SEARCH,
        value='"solo painter" "job quote" "United States"',
    )

    assert (
        SearchTool.build_query(product=product(), campaign=campaign(), source=source)
        == '"solo painter" "job quote" "United States"'
    )


def product() -> ProductRead:
    now = datetime.now(UTC)
    return ProductRead(
        id="product_test",
        product_name="Quote workflow",
        product_description="Mobile quoting workflow for home-service businesses.",
        target_customer="Residential painting companies",
        problem_being_solved="Painters need to create professional quotes after job walkthroughs.",
        value_proposition="Create customer-ready quotes faster.",
        target_geography="United States",
        validation_goal="Book discovery interviews.",
        qualification_criteria=[
            QualificationCriterion(
                id="criterion_fit",
                label="Residential painting company",
                description="Company provides painting services to homeowners.",
                weight=1,
                required=True,
                evidence_required=True,
            )
        ],
        preferred_discovery_sources=[
            DiscoverySource(type=DiscoverySourceType.WEB_SEARCH, value="residential painting companies")
        ],
        outreach_objective="Ask for a discovery conversation.",
        constraints=["Human approval required before sending."],
        created_at=now,
        updated_at=now,
    )


def campaign():
    from campaigns.schemas import CampaignRead

    now = datetime.now(UTC)
    return CampaignRead(
        id="campaign_test",
        product_id="product_test",
        name="Search query test",
        status="draft",
        stage="discovery",
        max_leads=10,
        channels=["email"],
        discovery_seeds=[],
        goal_override=None,
        created_at=now,
        updated_at=now,
    )
