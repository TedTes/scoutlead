from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignCreate
from canonical.website_enrichment import EnrichmentSummary
from db.session import create_database
from evaluation.digital_opportunity import opportunity_evidence_from_sources
from leads.repository import LeadRepository
from products.repository import ProductRepository
from products.schemas import ProductCreate, QualificationCriterion
from territories.opportunity_audit import (
    BusinessOpportunityAuditor,
    _credible_business_website,
)
from tools.search import SearchResult


def test_campaign_opportunity_audit_refreshes_existing_evidence(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class EmptySession:
        def scalars(self, statement):
            return []

    def fake_enrich(session, **kwargs):
        captured.update(kwargs)
        return EnrichmentSummary(dry_run=False)

    monkeypatch.setattr("territories.opportunity_audit.enrich_business_pool", fake_enrich)
    auditor = BusinessOpportunityAuditor(
        session=EmptySession(),
        verifier=None,
        timeout_seconds=1,
    )

    auditor.audit_campaign("campaign_test", category="painting", market="Toronto")

    assert captured["refresh"] is True


def test_campaign_opportunity_audit_keeps_unconfirmed_absence_low_confidence(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    monkeypatch.setattr(
        "territories.opportunity_audit.enrich_business_pool",
        lambda session, **kwargs: EnrichmentSummary(dry_run=False),
    )
    with session_factory() as session:
        product = ProductRepository(session).create(
            ProductCreate(
                product_name="Local Website Growth",
                product_description="Website improvements for local businesses.",
                target_customer="Independent home-service businesses",
                problem_being_solved="Missing websites and weak conversion flows.",
                value_proposition="Generate more customer inquiries.",
                target_geography="Toronto ON",
                qualification_criteria=[QualificationCriterion(label="Independent business")],
            )
        )
        campaign = CampaignRepository(session).create(
            CampaignCreate(
                product_id=product.id,
                name="No website businesses",
                source_input="painters Toronto ON",
                max_leads=10,
                channels=["manual"],
            )
        )
        lead = LeadRepository(session).create_from_search_result(
            campaign.id,
            product.id,
            {
                "title": "Neighborhood Painting",
                "url": None,
                "geography": "1 Main St, Toronto, ON",
                "source": "google_places",
                "raw": {
                    "businessStatus": "OPERATIONAL",
                    "nationalPhoneNumber": "(416) 555-0101",
                    "googleMapsUri": "https://maps.google.com/?cid=123",
                    "website_presence_label": "No website listed",
                },
            },
        )

        summary = BusinessOpportunityAuditor(
            session=session,
            verifier=None,
            timeout_seconds=1,
        ).audit_campaign(campaign.id, category="painting", market="Toronto")

        session.refresh(lead)
        opportunity = opportunity_evidence_from_sources(lead.raw_sources)
        assert opportunity is not None
        assert opportunity["level"] == "low"
        assert opportunity["signals"][0]["key"] == "no_website_listed"
        assert opportunity["signals"][0]["message"] == (
            "Google Business Profile has no website listed."
        )
        assert summary.high_digital_opportunity == 0


def test_website_confirmation_accepts_matching_site_and_rejects_directory() -> None:
    assert _credible_business_website(
        "https://northsidepainting.ca",
        "Northside Painting - Toronto",
        "Northside Painting Co.",
    ) == "https://northsidepainting.ca"
    assert _credible_business_website(
        "https://www.yelp.ca/biz/northside-painting",
        "Northside Painting Reviews",
        "Northside Painting Co.",
    ) is None


def test_campaign_opportunity_audit_confirms_no_website_found(monkeypatch) -> None:
    session_factory = _session_factory()
    monkeypatch.setattr(
        "territories.opportunity_audit.enrich_business_pool",
        lambda session, **kwargs: EnrichmentSummary(dry_run=False),
    )

    class EmptySearch:
        is_configured = True

        def lookup(self, query: str, limit: int = 5):
            return []

    with session_factory() as session:
        campaign, lead = _create_no_website_lead(session, website_policy="missing")
        BusinessOpportunityAuditor(
            session=session,
            verifier=None,
            search=EmptySearch(),
            timeout_seconds=1,
        ).audit_campaign(campaign.id, category="painting", market="Toronto")

        session.refresh(lead)
        opportunity = opportunity_evidence_from_sources(lead.raw_sources)
        assert opportunity is not None
        assert opportunity["level"] == "high"
        assert opportunity["signals"][0]["key"] == "no_website_found"


def test_campaign_opportunity_audit_excludes_site_found_during_confirmation(
    monkeypatch,
) -> None:
    session_factory = _session_factory()
    captured: dict[str, object] = {}

    def fake_enrich(session, **kwargs):
        captured.update(kwargs)
        return EnrichmentSummary(dry_run=False)

    monkeypatch.setattr("territories.opportunity_audit.enrich_business_pool", fake_enrich)

    class WebsiteSearch:
        is_configured = True

        def lookup(self, query: str, limit: int = 5):
            return [
                SearchResult(
                    title="Neighborhood Painting - Toronto",
                    url="https://neighborhoodpainting.ca",
                )
            ]

    with session_factory() as session:
        campaign, lead = _create_no_website_lead(session, website_policy="missing")
        BusinessOpportunityAuditor(
            session=session,
            verifier=None,
            search=WebsiteSearch(),
            timeout_seconds=1,
        ).audit_campaign(campaign.id, category="painting", market="Toronto")

        session.refresh(lead)
        opportunity = opportunity_evidence_from_sources(lead.raw_sources)
        assert lead.website_url == "https://neighborhoodpainting.ca"
        assert opportunity is not None
        assert opportunity["level"] == "none"
        assert opportunity["signals"][0]["key"] == "website_found_during_confirmation"
        assert captured["business_ids"] == []


def _session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _create_no_website_lead(session, *, website_policy: str):
    product = ProductRepository(session).create(
        ProductCreate(
            product_name="Local Website Growth",
            product_description="Website improvements for local businesses.",
            target_customer="Independent home-service businesses",
            problem_being_solved="Missing websites and weak conversion flows.",
            value_proposition="Generate more customer inquiries.",
            target_geography="Toronto ON",
            qualification_criteria=[QualificationCriterion(label="Independent business")],
        )
    )
    campaign = CampaignRepository(session).create(
        CampaignCreate(
            product_id=product.id,
            name="No website businesses",
            source_input="painters Toronto ON",
            source_inputs={"website_policy": website_policy},
            max_leads=10,
            channels=["manual"],
        )
    )
    lead = LeadRepository(session).create_from_search_result(
        campaign.id,
        product.id,
        {
            "title": "Neighborhood Painting",
            "url": None,
            "geography": "1 Main St, Toronto, ON",
            "source": "google_places",
            "raw": {
                "businessStatus": "OPERATIONAL",
                "nationalPhoneNumber": "(416) 555-0101",
                "googleMapsUri": "https://maps.google.com/?cid=123",
                "website_presence_label": "No website listed",
            },
        },
    )
    return campaign, lead
