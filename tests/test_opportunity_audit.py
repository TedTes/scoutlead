from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignCreate
from canonical.repository import CanonicalRepository
from canonical.website_enrichment import (
    BusinessWebsiteEnrichment,
    EnrichmentSummary,
)
from db.models import BusinessModel, SourceObservationModel
from db.session import create_database
from evaluation.digital_opportunity import opportunity_evidence_from_sources
from leads.repository import LeadRepository
from products.repository import ProductRepository
from products.schemas import ProductCreate, QualificationCriterion
from territories.opportunity_audit import (
    BusinessOpportunityAuditor,
    _business_domain_matches,
    _credible_business_website,
    _google_lists_no_website,
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


def test_campaign_opportunity_audit_keeps_unconfirmed_absence_reviewable(monkeypatch) -> None:
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
        assert opportunity["level"] == "moderate"
        assert opportunity["score"] == 35
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
        business_location="Toronto, ON",
    ) == "https://northsidepainting.ca"
    assert _credible_business_website(
        "https://ctpainters.ca",
        "CT Painters | Toronto & GTA",
        "CT Painters",
        business_location="Toronto, ON",
    ) == "https://ctpainters.ca"
    assert _credible_business_website(
        "https://www.yelp.ca/biz/northside-painting",
        "Northside Painting Reviews",
        "Northside Painting Co.",
    ) is None
    assert _credible_business_website(
        "https://www.profilecanada.com/northside-painting",
        "Northside Painting",
        "Northside Painting Co.",
    ) is None
    assert _credible_business_website(
        "https://ecopainting.ca/",
        "ECO Painting Services - Toronto",
        "ECO Painting Services",
        business_location="Toronto, ON",
    ) == "https://ecopainting.ca/"
    assert _credible_business_website(
        "https://www.pinotspalette.com/toronto",
        "Paint and Sip in Toronto",
        "Time to paint",
        business_location="Toronto, ON",
    ) is None
    assert _credible_business_website(
        "https://news.yahoo.com/painting-services-toronto",
        "Painting Services Toronto",
        "Painting Services Toronto",
    ) is None
    assert _credible_business_website(
        "https://lionheartpaintingks.com",
        "Lionheart Painting - Olathe, Kansas",
        "Lionheart Painting & Decorating Inc",
        business_location="Toronto, ON",
    ) is None
    assert _credible_business_website(
        "https://www.angleseypremiertouchpainting.com",
        "Premier Touch Painting Anglesey",
        "Premier Touch Painting",
        business_location="Toronto, ON",
    ) is None
    assert _credible_business_website(
        "https://www.handypro.com/service-categories/handyman-services",
        "HandyPro Handyman Services",
        "Pro Handyman",
        business_location="Toronto, ON",
    ) is None


def test_google_website_detection_reads_nested_discovery_payload() -> None:
    source = {
        "_observation_source": "google_places",
        "candidate_id": "candidate_test",
        "raw": {
            "title": "Prestige Painting & Contracting Ltd.",
            "raw": {
                "websiteUri": "https://www.prestigepaintinggta.ca/",
                "businessStatus": "OPERATIONAL",
            },
        },
    }

    assert _google_lists_no_website([source]) is False


def test_contact_domain_identity_rejects_unrelated_businesses() -> None:
    assert _business_domain_matches("CT Painters", "ctpainters.ca")
    assert _business_domain_matches(
        "Paint & Drywall Guys Toronto", "paintingdrywalltoronto.ca"
    )
    assert not _business_domain_matches("Time to paint", "pinotspalette.com")
    assert not _business_domain_matches(
        "Scarborough Painting Company", "altonapainting.com"
    )
    assert not _business_domain_matches("Prime Painting Toronto", "gmail.com")


def test_business_audit_confirms_matching_contact_domain(monkeypatch) -> None:
    session_factory = _session_factory()
    monkeypatch.setattr(
        "territories.opportunity_audit.enrich_business_pool",
        lambda session, **kwargs: EnrichmentSummary(dry_run=False),
    )
    monkeypatch.setattr(
        "territories.opportunity_audit.WebsiteEnrichmentClient.inspect",
        _active_website_inspection,
    )
    with session_factory() as session:
        link = CanonicalRepository(session).upsert_from_discovery_result(
            company_name="CT Painters",
            website_url=None,
            contact_email="contact@ctpainters.ca",
            geography="Toronto, ON",
            source="google_places",
            raw={
                "businessStatus": "OPERATIONAL",
                "nationalPhoneNumber": "4165550101",
                "googleMapsUri": "https://maps.google.com/?cid=123",
            },
        )
        business = session.get(BusinessModel, link.business_id)
        assert business is not None

        BusinessOpportunityAuditor(
            session=session,
            verifier=None,
            timeout_seconds=1,
        ).audit_businesses(
            [business.id],
            category="painting",
            market="Toronto",
            opportunity_policy="weak_or_missing",
        )

        session.refresh(business)
        assert business.website_url == "https://ctpainters.ca"


def test_business_audit_restores_nested_google_website(monkeypatch) -> None:
    session_factory = _session_factory()
    captured: dict[str, object] = {}

    def fake_enrich(session, **kwargs):
        captured.update(kwargs)
        return EnrichmentSummary(dry_run=False)

    monkeypatch.setattr("territories.opportunity_audit.enrich_business_pool", fake_enrich)
    with session_factory() as session:
        link = CanonicalRepository(session).upsert_from_discovery_result(
            company_name="Prestige Painting & Contracting Ltd.",
            website_url=None,
            geography="North York, ON",
            source="google_places",
            raw={
                "raw": {
                    "raw": {
                        "websiteUri": "https://www.prestigepaintinggta.ca/",
                        "businessStatus": "OPERATIONAL",
                    }
                }
            },
        )
        business = session.get(BusinessModel, link.business_id)
        assert business is not None

        BusinessOpportunityAuditor(
            session=session,
            verifier=None,
            timeout_seconds=1,
        ).audit_businesses(
            [business.id],
            category="painting",
            market="Toronto",
            opportunity_policy="weak_or_missing",
        )

        session.refresh(business)
        latest = session.query(SourceObservationModel).filter_by(
            business_id=business.id,
            source="website_presence_check",
        ).one()
        assert business.website_url == "https://www.prestigepaintinggta.ca/"
        assert business.domain == "prestigepaintinggta.ca"
        assert latest.raw_payload["digital_opportunity"]["signals"][0]["key"] == (
            "website_found_during_confirmation"
        )
        assert captured["business_ids"] == [business.id]


def test_campaign_opportunity_audit_records_completed_confirmation_search(monkeypatch) -> None:
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
        assert opportunity["level"] == "moderate"
        assert opportunity["signals"][0]["key"] == "no_website_found"
        assert opportunity["signals"][0]["value"] == "Website not confirmed"


def test_google_no_website_observation_repairs_polluted_canonical_url(monkeypatch) -> None:
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
        link = CanonicalRepository(session).upsert_from_discovery_result(
            company_name="Time to paint",
            website_url=None,
            geography="Toronto, ON",
            source="google_places",
            raw={
                "businessStatus": "OPERATIONAL",
                "nationalPhoneNumber": "(416) 555-0101",
                "googleMapsUri": "https://maps.google.com/?cid=123",
                "website_url": None,
            },
        )
        business = session.get(BusinessModel, link.business_id)
        assert business is not None
        business.website_url = "https://www.pinotspalette.com/toronto"
        business.domain = "pinotspalette.com"
        session.commit()

        BusinessOpportunityAuditor(
            session=session,
            verifier=None,
            search=EmptySearch(),
            timeout_seconds=1,
        ).audit_businesses(
            [business.id],
            category="painting",
            market="Toronto",
            opportunity_policy="weak_or_missing",
        )

        session.refresh(business)
        latest = session.query(SourceObservationModel).filter_by(
            business_id=business.id,
            source="website_presence_check",
        ).one()
        assert business.website_url is None
        assert latest.raw_payload["digital_opportunity"]["signals"][0]["key"] == (
            "no_website_found"
        )


def test_google_omission_preserves_url_supported_by_trusted_observation(monkeypatch) -> None:
    session_factory = _session_factory()
    monkeypatch.setattr(
        "territories.opportunity_audit.enrich_business_pool",
        lambda session, **kwargs: EnrichmentSummary(dry_run=False),
    )
    with session_factory() as session:
        canonical = CanonicalRepository(session)
        link = canonical.upsert_from_discovery_result(
            company_name="Luke's Painting",
            website_url="https://lukekushspainting.example",
            geography="Toronto, ON",
            source="google_places_seed",
            raw={
                "id": "places/luke",
                "businessStatus": "OPERATIONAL",
                "nationalPhoneNumber": "416-555-0101",
                "website_url": "https://lukekushspainting.example",
            },
        )
        business = session.get(BusinessModel, link.business_id)
        assert business is not None
        canonical.record_business_evidence(
            business=business,
            source="google_places",
            raw={
                "businessStatus": "OPERATIONAL",
                "nationalPhoneNumber": "416-555-0101",
                "googleMapsUri": "https://maps.google.com/?cid=456",
            },
        )
        session.commit()

        BusinessOpportunityAuditor(
            session=session,
            verifier=None,
            timeout_seconds=1,
        ).audit_businesses(
            [business.id],
            category="painting",
            market="Toronto",
            opportunity_policy="weak_or_missing",
        )

        session.refresh(business)
        assert business.website_url == "https://lukekushspainting.example"
        assert not session.query(SourceObservationModel).filter_by(
            business_id=business.id,
            source="website_presence_check",
        ).all()


def test_campaign_opportunity_audit_excludes_site_found_during_confirmation(
    monkeypatch,
) -> None:
    session_factory = _session_factory()
    captured: dict[str, object] = {}

    def fake_enrich(session, **kwargs):
        captured.update(kwargs)
        return EnrichmentSummary(dry_run=False)

    monkeypatch.setattr("territories.opportunity_audit.enrich_business_pool", fake_enrich)
    monkeypatch.setattr(
        "territories.opportunity_audit.WebsiteEnrichmentClient.inspect",
        _active_website_inspection,
    )

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


def test_website_confirmation_retries_with_a_broader_query(monkeypatch) -> None:
    session_factory = _session_factory()
    monkeypatch.setattr(
        "territories.opportunity_audit.enrich_business_pool",
        lambda session, **kwargs: EnrichmentSummary(dry_run=False),
    )
    monkeypatch.setattr(
        "territories.opportunity_audit.WebsiteEnrichmentClient.inspect",
        _active_website_inspection,
    )

    class ProgressiveSearch:
        is_configured = True

        def __init__(self) -> None:
            self.queries: list[str] = []

        def lookup(self, query: str, limit: int = 5):
            self.queries.append(query)
            if len(self.queries) == 1:
                return []
            return [
                SearchResult(
                    title="Neighborhood Painting - Toronto",
                    url="https://neighborhoodpainting.ca",
                )
            ]

    search = ProgressiveSearch()
    with session_factory() as session:
        campaign, lead = _create_no_website_lead(session, website_policy="missing")
        BusinessOpportunityAuditor(
            session=session,
            verifier=None,
            search=search,
            timeout_seconds=1,
        ).audit_campaign(campaign.id, category="painting", market="Toronto")

        session.refresh(lead)
        assert lead.website_url == "https://neighborhoodpainting.ca"
        assert len(search.queries) == 2


def test_website_confirmation_rejects_a_stale_matching_domain(monkeypatch) -> None:
    session_factory = _session_factory()
    monkeypatch.setattr(
        "territories.opportunity_audit.enrich_business_pool",
        lambda session, **kwargs: EnrichmentSummary(dry_run=False),
    )
    monkeypatch.setattr(
        "territories.opportunity_audit.WebsiteEnrichmentClient.inspect",
        _unavailable_website_inspection,
    )

    class StaleWebsiteSearch:
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
            search=StaleWebsiteSearch(),
            timeout_seconds=1,
        ).audit_campaign(campaign.id, category="painting", market="Toronto")

        session.refresh(lead)
        opportunity = opportunity_evidence_from_sources(lead.raw_sources)
        assert lead.website_url is None
        assert opportunity is not None
        assert opportunity["signals"][0]["key"] == "no_website_found"


def _active_website_inspection(inspector, business):
    return _website_inspection(
        business,
        availability_status="active",
        inspected_urls=[business.website_url],
    )


def _unavailable_website_inspection(inspector, business):
    return _website_inspection(
        business,
        availability_status="unavailable",
        inspected_urls=[],
    )


def _website_inspection(business, *, availability_status, inspected_urls):
    return BusinessWebsiteEnrichment(
        business_id=business.id,
        company_name=business.display_name,
        website_url=business.website_url,
        inspected_urls=inspected_urls,
        emails=[],
        best_email=None,
        phones=[],
        contact_name=None,
        contact_role=None,
        has_contact_form=False,
        has_quote_form=False,
        has_booking_form=False,
        uses_https=True,
        has_mobile_viewport=True,
        quote_signals=[],
        service_signals=[],
        source_url=business.website_url,
        description="",
        errors=[],
        availability_status=availability_status,
        availability_reason="",
    )


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
