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


def test_strict_missing_website_results_require_confirmed_absence_signal() -> None:
    campaign = _campaign(requested_count=5, website_policy="missing")
    leads = [
        _lead("confirmed-absent", opportunity_score=65, level="high", signal="no_website_found"),
        _lead("site-found", opportunity_score=0, level="none", signal="website_found_during_confirmation"),
        _lead("unavailable", opportunity_score=65, level="high", signal="website_unavailable"),
    ]

    selected = select_campaign_results(campaign, leads)

    assert [lead.id for lead in selected] == ["confirmed-absent"]


def test_missing_or_unavailable_results_reject_active_website_signals() -> None:
    campaign = _campaign(requested_count=5, website_policy="missing_or_unavailable")
    leads = [
        _lead("confirmed-absent", opportunity_score=65, level="high", signal="no_website_found"),
        _lead("unavailable", opportunity_score=65, level="high", signal="website_unavailable"),
        _lead("parked", opportunity_score=65, level="high", signal="website_parked"),
        _lead("missing-form", opportunity_score=30, level="moderate", signal="missing_quote_or_booking_form"),
    ]

    selected = select_campaign_results(campaign, leads)

    assert {lead.id for lead in selected} == {"confirmed-absent", "unavailable", "parked"}


def test_opportunity_results_exclude_disqualified_businesses() -> None:
    campaign = _campaign(requested_count=5, website_policy="missing")
    leads = [
        _lead("qualified", opportunity_score=65, level="high", signal="no_website_found"),
        _lead(
            "chain",
            opportunity_score=65,
            level="high",
            signal="no_website_found",
            status=LeadStatus.DISQUALIFIED,
        ),
    ]

    assert [lead.id for lead in select_campaign_results(campaign, leads)] == ["qualified"]


def _campaign(
    *,
    requested_count: int,
    requires_opportunity: bool = True,
    website_policy: str = "any",
) -> CampaignRead:
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
            "website_policy": website_policy,
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
    signal: str | None = None,
    status: LeadStatus = LeadStatus.RESEARCHED,
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
                    "signals": [{"key": signal}] if signal else [],
                }
            }
        ],
        status=status,
        verification_status=verification_status,
        created_at=now,
        updated_at=now,
    )
