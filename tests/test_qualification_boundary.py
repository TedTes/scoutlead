from datetime import UTC, datetime

from leads.schemas import CriterionScore, LeadFitType, LeadRead, LeadResearch, LeadStatus, QualificationResult
from products.schemas import DiscoverySource, DiscoverySourceType, ProductRead, QualificationCriterion
from workflows.qualification import MIN_QUALIFICATION_SCORE, enforce_qualification_boundary


def test_low_score_cannot_be_qualified_for_outreach() -> None:
    result = QualificationResult(
        qualified=True,
        score=6,
        rationale="Some keywords matched.",
        criteria=[],
        recommended_next_step="Draft outreach.",
    )

    guarded = enforce_qualification_boundary(product(), lead(), result)

    assert guarded.qualified is False
    assert guarded.score == 6
    assert f"{MIN_QUALIFICATION_SCORE} qualification threshold" in guarded.rationale
    assert guarded.recommended_next_step == "Do not send outreach."


def test_competitor_or_vendor_classification_cannot_be_qualified_for_outreach() -> None:
    result = QualificationResult(
        qualified=True,
        score=92,
        rationale="Looks relevant.",
        criteria=[
            CriterionScore(
                criterion_id="criterion_fit",
                label="Matches target customer",
                score=92,
                evidence=["Mentions the same workflow"],
            )
        ],
        recommended_next_step="Draft outreach.",
    )
    competitor_lead = lead(
        research=LeadResearch(
            summary="This is a competing quoting product, not a painting business.",
            lead_type=LeadFitType.COMPETITOR_OR_ALTERNATIVE,
            business_type="Quoting software vendor",
            geography="United States",
            website_url="https://quote-tool.example",
            signals=["Sells quoting software"],
            pain_indicators=[],
            disqualifiers=[],
            sources=["https://quote-tool.example"],
            confidence=90,
        )
    )

    guarded = enforce_qualification_boundary(product(), competitor_lead, result)

    assert guarded.qualified is False
    assert guarded.score == 25
    assert "not a target customer" in guarded.rationale
    assert guarded.recommended_next_step == "Do not send outreach."


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


def lead(research: LeadResearch | None = None) -> LeadRead:
    now = datetime.now(UTC)
    return LeadRead(
        id="lead_test",
        campaign_id="campaign_test",
        product_id="product_test",
        company_name="Candidate",
        website_url="https://candidate.example",
        contact_email=None,
        geography="United States",
        description="Candidate lead",
        source="search",
        raw_sources=[],
        status=LeadStatus.RESEARCHED,
        research=research
        or LeadResearch(
            summary="Residential painting business.",
            lead_type=LeadFitType.TARGET_CUSTOMER,
            business_type="Residential painting company",
            geography="United States",
            website_url="https://candidate.example",
            signals=["Offers residential painting"],
            pain_indicators=["Offers quotes"],
            disqualifiers=[],
            sources=["https://candidate.example"],
            confidence=80,
        ),
        qualification=None,
        created_at=now,
        updated_at=now,
    )
