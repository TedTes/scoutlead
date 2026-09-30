from datetime import UTC, datetime

from campaigns.schemas import CampaignRead
from leads.schemas import ContactVerificationStatus, LeadRead, LeadStatus
from leads.selection import select_campaign_results


def test_opportunity_results_filter_rank_and_limit() -> None:
    campaign = _campaign(requested_count=2)
    leads = [
        _lead("low", opportunity_score=15, level="low", email="low@example.com"),
        _lead("moderate-unverified", opportunity_score=30, level="moderate"),
        _lead(
            "moderate-verified",
            opportunity_score=30,
            level="moderate",
            email="verified@example.com",
            verification_status=ContactVerificationStatus.VALID,
        ),
        _lead("high", opportunity_score=55, level="high"),
    ]

    selected = select_campaign_results(campaign, leads)

    assert [lead.id for lead in selected] == ["high", "moderate-verified"]


def test_standard_results_are_not_opportunity_filtered() -> None:
    campaign = _campaign(requested_count=1, requires_opportunity=False)
    leads = [_lead("first", opportunity_score=0, level="none"), _lead("second", opportunity_score=0, level="none")]

    assert select_campaign_results(campaign, leads) == leads


def _campaign(*, requested_count: int, requires_opportunity: bool = True) -> CampaignRead:
    now = datetime.now(UTC)
    return CampaignRead(
        id="campaign_test",
        product_id="product_test",
        name="Test search",
        goal_type="learn",
        status="completed",
        stage="complete",
        max_leads=50,
        channels=["manual"],
        discovery_seeds=[],
        source_inputs={
            "requires_digital_opportunity": requires_opportunity,
            "requested_result_count": requested_count,
        },
        created_at=now,
        updated_at=now,
    )


def _lead(
    lead_id: str,
    *,
    opportunity_score: int,
    level: str,
    email: str | None = None,
    verification_status: ContactVerificationStatus = ContactVerificationStatus.UNVERIFIED,
) -> LeadRead:
    now = datetime.now(UTC)
    return LeadRead(
        id=lead_id,
        campaign_id="campaign_test",
        product_id="product_test",
        company_name=lead_id,
        website_url=f"https://{lead_id}.example",
        contact_email=email,
        source="google_places",
        raw_sources=[
            {
                "digital_opportunity": {
                    "version": 1,
                    "score": opportunity_score,
                    "level": level,
                    "signals": [],
                }
            }
        ],
        status=LeadStatus.RESEARCHED,
        verification_status=verification_status,
        created_at=now,
        updated_at=now,
    )
