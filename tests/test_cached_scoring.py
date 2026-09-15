from datetime import UTC, datetime

from evaluation.lead_scoring import score_cached_lead
from leads.schemas import AgentFitStatus, ContactVerificationStatus, LeadRead, LeadStatus
from products.schemas import DiscoverySource, DiscoverySourceType, ProductRead, QualificationCriterion


def test_cached_fit_score_does_not_increase_for_email() -> None:
    product = _product()
    row = _cached_row()
    without_email = _lead(contact_email=None)
    with_email = _lead(contact_email="info@cedarpainting.example")

    no_email_result = score_cached_lead(
        product=product,
        lead=without_email,
        row=row,
        confidence=92,
    )
    email_result = score_cached_lead(
        product=product,
        lead=with_email,
        row=row,
        confidence=92,
    )

    assert no_email_result.score_breakdown is not None
    assert email_result.score_breakdown is not None
    assert email_result.score_breakdown.fit_score == no_email_result.score_breakdown.fit_score
    assert email_result.score == no_email_result.score
    assert email_result.score < 95
    assert email_result.score_breakdown.reachability_score > no_email_result.score_breakdown.reachability_score


def test_cached_directory_result_with_email_is_not_good_fit() -> None:
    result = score_cached_lead(
        product=_product(),
        lead=_lead(contact_email="info@yelp.example", website_url="https://www.yelp.com/biz/cedar-painting"),
        row={
            **_cached_row(),
            "source": "web_search",
            "url": "https://www.yelp.com/biz/cedar-painting",
            "snippet": "Best residential painting reviews and contact details.",
        },
        confidence=92,
    )

    assert result.qualified is False
    assert result.fit_status == AgentFitStatus.NOT_FIT
    assert result.score <= 35
    assert any("Directory" in risk for risk in result.risks)


def test_cached_category_match_without_quote_workflow_is_not_penalized_as_missing() -> None:
    row = _cached_row()
    row["raw"] = {
        **row["raw"],
        "website_enrichment": {
            "service_signals": ["residential painting", "interior painting", "commercial painting"],
            "has_contact_form": True,
            "inspected_urls": ["https://cedarpainting.example"],
        },
    }
    result = score_cached_lead(
        product=_product(),
        lead=_lead(contact_email="info@cedarpainting.example"),
        row=row,
        confidence=95,
    )

    assert result.score_breakdown is not None
    assert result.score_breakdown.fit_score > 74
    assert all("quote or estimate workflow" not in item.lower() for item in result.missing_evidence)


def test_cached_invalid_email_lowers_reachability_not_fit() -> None:
    product = _product()
    row = _cached_row()
    valid = score_cached_lead(
        product=product,
        lead=_lead(
            contact_email="info@cedarpainting.example",
            verification_status=ContactVerificationStatus.VALID,
        ),
        row=row,
        confidence=92,
    )
    invalid = score_cached_lead(
        product=product,
        lead=_lead(
            contact_email="info@cedarpainting.example",
            verification_status=ContactVerificationStatus.INVALID,
        ),
        row=row,
        confidence=92,
    )

    assert valid.score_breakdown is not None
    assert invalid.score_breakdown is not None
    assert valid.score_breakdown.fit_score == invalid.score_breakdown.fit_score
    assert valid.score == invalid.score
    assert invalid.score_breakdown.reachability_score < valid.score_breakdown.reachability_score


def _product() -> ProductRead:
    now = datetime.now(UTC)
    return ProductRead(
        id="product_test",
        product_name="Customer discovery tool",
        product_description="Find and review local businesses that match a product's target customer.",
        target_customer="Residential painting contractors",
        problem_being_solved="Preparing quotes after walkthroughs is slow.",
        value_proposition="Find relevant contacts for customer discovery.",
        target_geography="Canada",
        validation_goal="Find relevant contacts.",
        qualification_criteria=[
            QualificationCriterion(
                id="residential_painter",
                label="Residential painting contractor",
                required=True,
                evidence_required=True,
            )
        ],
        preferred_discovery_sources=[
            DiscoverySource(type=DiscoverySourceType.WEB_SEARCH, value="residential painting contractors")
        ],
        outreach_objective="Ask for a customer discovery conversation.",
        constraints=["Human approval required before sending."],
        created_at=now,
        updated_at=now,
    )


def _lead(
    *,
    contact_email: str | None,
    website_url: str = "https://cedarpainting.example",
    verification_status: ContactVerificationStatus = ContactVerificationStatus.UNVERIFIED,
) -> LeadRead:
    now = datetime.now(UTC)
    return LeadRead(
        id="lead_test",
        campaign_id="campaign_test",
        product_id="product_test",
        company_name="Cedar Painting",
        website_url=website_url,
        contact_email=contact_email,
        geography="Toronto, ON, Canada",
        description="Residential painting contractor offering interior painting and free quotes.",
        source="google_places",
        raw_sources=[],
        status=LeadStatus.DISCOVERED,
        verification_status=verification_status,
        created_at=now,
        updated_at=now,
    )


def _cached_row() -> dict:
    return {
        "title": "Cedar Painting",
        "url": "https://cedarpainting.example",
        "snippet": "Residential painting contractor offering interior painting and free quotes in Toronto.",
        "geography": "Toronto, ON, Canada",
        "source": "google_places",
        "raw": {
            "canonical_business_id": "business_test",
            "nationalPhoneNumber": "(416) 555-1212",
            "website_enrichment": {
                "service_signals": ["residential painting", "interior painting"],
                "quote_signals": ["free quotes"],
                "has_contact_form": True,
                "has_quote_form": True,
                "inspected_urls": ["https://cedarpainting.example"],
            },
        },
    }
