import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from db.models import BusinessModel, ContactModel, SourceObservationModel
from db.session import create_database
from canonical.website_enrichment import (
    SOURCE_NAME,
    cleanup_placeholder_emails,
    enrich_business_pool,
)
from seeding.service import BusinessSeedService
from tests.test_business_seeding import painting_seed


def test_website_enrichment_creates_contact_and_source_observation(monkeypatch) -> None:
    session_factory = _session_factory()

    with session_factory() as session:
        BusinessSeedService(session).import_seeds(
            [
                painting_seed(
                    contact_email=None,
                    contact_name=None,
                    website_url="https://paint.testsite.ca",
                )
            ],
            batch_id="painting-toronto-v1",
        )
        original_business = session.scalar(select(BusinessModel))
        assert original_business is not None
        original_semantic_text = original_business.semantic_text

        monkeypatch.setattr("canonical.website_enrichment.httpx.get", fake_get)

        summary = enrich_business_pool(
            session,
            category="painting",
            market="toronto",
            limit=1,
            dry_run=False,
            timeout_seconds=0.1,
            page_delay_seconds=0,
        )

        assert summary.selected == 1
        assert summary.reachable == 1
        assert summary.with_email == 1
        assert summary.with_quote_signal == 1
        assert summary.written == 1

        business = session.scalar(select(BusinessModel))
        assert business is not None
        assert business.semantic_text == original_semantic_text

        contact = session.scalar(select(ContactModel).where(ContactModel.email.is_not(None)))
        assert contact is not None
        assert contact.email == "owner@paint.testsite.ca"
        assert contact.business_id == business.id

        observation = session.scalar(
            select(SourceObservationModel).where(SourceObservationModel.source == SOURCE_NAME)
        )
        assert observation is not None
        assert observation.business_id == business.id
        assert observation.raw_payload["website_enrichment"]["best_email"] == "owner@paint.testsite.ca"
        assert observation.raw_payload["website_enrichment"]["has_quote_form"] is True
        assert observation.raw_payload["digital_opportunity"]["score"] == 15
        assert observation.raw_payload["digital_opportunity"]["level"] == "low"


def test_website_enrichment_records_review_and_conversion_opportunity(monkeypatch) -> None:
    session_factory = _session_factory()

    with session_factory() as session:
        BusinessSeedService(session).import_seeds(
            [
                painting_seed(
                    contact_email=None,
                    contact_name=None,
                    website_url="https://quiet.example",
                    source="google_places_seed",
                    source_url="https://maps.example/quiet",
                    raw={
                        "google_places": {
                            "rating": 4.1,
                            "userRatingCount": 8,
                        }
                    },
                )
            ],
            batch_id="painting-toronto-v1",
        )

        monkeypatch.setattr("canonical.website_enrichment.httpx.get", fake_no_signal_get)

        summary = enrich_business_pool(
            session,
            category="painting",
            market="toronto",
            limit=1,
            dry_run=False,
            mark_attempted=True,
            timeout_seconds=0.1,
            page_delay_seconds=0,
        )

        observation = session.scalar(
            select(SourceObservationModel).where(SourceObservationModel.source == SOURCE_NAME)
        )
        assert observation is not None
        opportunity = observation.raw_payload["digital_opportunity"]
        assert opportunity["score"] == 80
        assert opportunity["level"] == "high"
        assert opportunity["google_rating"] == 4.1
        assert opportunity["google_review_count"] == 8
        assert summary.with_digital_opportunity == 1
        assert summary.high_digital_opportunity == 1


def test_website_enrichment_dry_run_does_not_write(monkeypatch) -> None:
    session_factory = _session_factory()

    with session_factory() as session:
        BusinessSeedService(session).import_seeds(
            [
                painting_seed(
                    contact_email=None,
                    contact_name=None,
                    website_url="https://paint.testsite.ca",
                )
            ],
            batch_id="painting-toronto-v1",
        )

        monkeypatch.setattr("canonical.website_enrichment.httpx.get", fake_get)

        summary = enrich_business_pool(
            session,
            category="painting",
            market="toronto",
            limit=1,
            dry_run=True,
            timeout_seconds=0.1,
            page_delay_seconds=0,
        )

        assert summary.with_email == 1
        assert summary.written == 0
        assert session.scalar(select(ContactModel).where(ContactModel.email.is_not(None))) is None
        assert (
            session.scalar(select(SourceObservationModel).where(SourceObservationModel.source == SOURCE_NAME))
            is None
        )


def test_website_enrichment_records_opportunity_without_contact_signal(monkeypatch) -> None:
    session_factory = _session_factory()

    with session_factory() as session:
        BusinessSeedService(session).import_seeds(
            [
                painting_seed(
                    contact_email=None,
                    contact_name=None,
                    website_url="https://quiet.example",
                )
            ],
            batch_id="painting-toronto-v1",
        )

        monkeypatch.setattr("canonical.website_enrichment.httpx.get", fake_no_signal_get)

        summary = enrich_business_pool(
            session,
            category="painting",
            market="toronto",
            limit=1,
            dry_run=False,
            timeout_seconds=0.1,
            page_delay_seconds=0,
        )

        assert summary.selected == 1
        assert summary.skipped == 0
        assert summary.with_digital_opportunity == 1
        assert summary.written == 1
        assert session.scalar(select(ContactModel).where(ContactModel.email.is_not(None))) is None
        assert (
            session.scalar(select(SourceObservationModel).where(SourceObservationModel.source == SOURCE_NAME))
            is not None
        )

        second = enrich_business_pool(
            session,
            category="painting",
            market="toronto",
            limit=1,
            dry_run=False,
            timeout_seconds=0.1,
            page_delay_seconds=0,
        )

        assert second.selected == 0


def test_unavailable_website_is_high_opportunity_in_availability_lane(monkeypatch) -> None:
    session_factory = _session_factory()
    calls: list[str] = []

    class NotFoundResponse:
        def __init__(self, url: str) -> None:
            self.url = url
            self.status_code = 404

        def raise_for_status(self) -> None:
            request = httpx.Request("GET", self.url)
            response = httpx.Response(404, request=request)
            raise httpx.HTTPStatusError(
                "Not found",
                request=request,
                response=response,
            )

    def not_found(url: str, **kwargs):
        del kwargs
        calls.append(url)
        return NotFoundResponse(url)

    with session_factory() as session:
        BusinessSeedService(session).import_seeds(
            [
                painting_seed(
                    contact_email=None,
                    contact_name=None,
                    website_url="https://dead-painter.example",
                )
            ],
            batch_id="painting-toronto-v1",
        )
        monkeypatch.setattr("canonical.website_enrichment.httpx.get", not_found)

        summary = enrich_business_pool(
            session,
            category="painting",
            market="toronto",
            limit=1,
            timeout_seconds=0.1,
            page_delay_seconds=0,
            opportunity_policy="missing_or_unavailable",
        )

        observation = session.scalar(
            select(SourceObservationModel).where(SourceObservationModel.source == SOURCE_NAME)
        )
        assert observation is not None
        assert observation.raw_payload["website_enrichment"]["availability_status"] == "unavailable"
        assert observation.raw_payload["digital_opportunity"]["signals"][0]["key"] == (
            "website_unavailable"
        )
        assert summary.high_digital_opportunity == 1
        assert calls == ["https://dead-painter.example", "http://dead-painter.example"]


def test_active_website_is_excluded_from_availability_lane(monkeypatch) -> None:
    session_factory = _session_factory()

    with session_factory() as session:
        BusinessSeedService(session).import_seeds(
            [
                painting_seed(
                    contact_email=None,
                    contact_name=None,
                    website_url="https://quiet.example",
                )
            ],
            batch_id="painting-toronto-v1",
        )
        monkeypatch.setattr("canonical.website_enrichment.httpx.get", fake_no_signal_get)

        enrich_business_pool(
            session,
            category="painting",
            market="toronto",
            limit=1,
            timeout_seconds=0.1,
            max_pages_per_business=1,
            page_delay_seconds=0,
            opportunity_policy="missing_or_unavailable",
            mark_attempted=True,
        )

        observation = session.scalar(
            select(SourceObservationModel).where(SourceObservationModel.source == SOURCE_NAME)
        )
        assert observation is not None
        assert observation.raw_payload["website_enrichment"]["availability_status"] == "active"
        assert observation.raw_payload["digital_opportunity"]["score"] == 0
        assert observation.raw_payload["digital_opportunity"]["level"] == "none"


def test_weak_or_missing_lane_keeps_active_site_with_no_conversion_form(monkeypatch) -> None:
    session_factory = _session_factory()

    with session_factory() as session:
        BusinessSeedService(session).import_seeds(
            [
                painting_seed(
                    contact_email=None,
                    contact_name=None,
                    website_url="https://quiet.example",
                )
            ],
            batch_id="painting-toronto-v1",
        )
        monkeypatch.setattr("canonical.website_enrichment.httpx.get", fake_no_signal_get)

        enrich_business_pool(
            session,
            category="painting",
            market="toronto",
            limit=1,
            timeout_seconds=0.1,
            max_pages_per_business=1,
            page_delay_seconds=0,
            opportunity_policy="weak_or_missing",
            mark_attempted=True,
        )

        observation = session.scalar(
            select(SourceObservationModel).where(SourceObservationModel.source == SOURCE_NAME)
        )
        assert observation is not None
        opportunity = observation.raw_payload["digital_opportunity"]
        assert opportunity["score"] >= 30
        assert "missing_quote_or_booking_form" in {
            signal["key"] for signal in opportunity["signals"]
        }


def test_parked_website_is_high_opportunity_in_availability_lane(monkeypatch) -> None:
    session_factory = _session_factory()

    with session_factory() as session:
        BusinessSeedService(session).import_seeds(
            [
                painting_seed(
                    contact_email=None,
                    contact_name=None,
                    website_url="https://parked.example",
                )
            ],
            batch_id="painting-toronto-v1",
        )
        monkeypatch.setattr(
            "canonical.website_enrichment.httpx.get",
            lambda url, **kwargs: FakeResponse(
                url,
                "<html><body>This domain is parked. Buy this domain.</body></html>",
            ),
        )

        enrich_business_pool(
            session,
            category="painting",
            market="toronto",
            limit=1,
            max_pages_per_business=1,
            page_delay_seconds=0,
            opportunity_policy="missing_or_unavailable",
        )

        observation = session.scalar(
            select(SourceObservationModel).where(SourceObservationModel.source == SOURCE_NAME)
        )
        assert observation is not None
        assert observation.raw_payload["website_enrichment"]["availability_status"] == "parked"
        assert observation.raw_payload["digital_opportunity"]["signals"][0]["key"] == (
            "website_parked"
        )


def test_timeouts_are_inconclusive_not_dead_website_evidence(monkeypatch) -> None:
    session_factory = _session_factory()

    def timeout(url: str, **kwargs):
        del url, kwargs
        raise httpx.ReadTimeout("timed out")

    with session_factory() as session:
        BusinessSeedService(session).import_seeds(
            [
                painting_seed(
                    contact_email=None,
                    contact_name=None,
                    website_url="https://slow.example",
                )
            ],
            batch_id="painting-toronto-v1",
        )
        monkeypatch.setattr("canonical.website_enrichment.httpx.get", timeout)

        enrich_business_pool(
            session,
            category="painting",
            market="toronto",
            limit=1,
            page_delay_seconds=0,
            opportunity_policy="missing_or_unavailable",
            mark_attempted=True,
        )

        observation = session.scalar(
            select(SourceObservationModel).where(SourceObservationModel.source == SOURCE_NAME)
        )
        assert observation is not None
        assert observation.raw_payload["website_enrichment"]["availability_status"] == (
            "inconclusive"
        )
        assert observation.raw_payload["digital_opportunity"]["score"] == 0


def test_weak_or_missing_timeout_is_inconclusive(monkeypatch) -> None:
    session_factory = _session_factory()

    def timeout(url: str, **kwargs):
        del url, kwargs
        raise httpx.ReadTimeout("timed out")

    with session_factory() as session:
        BusinessSeedService(session).import_seeds(
            [
                painting_seed(
                    contact_email=None,
                    contact_name=None,
                    website_url="https://slow.example",
                )
            ],
            batch_id="painting-toronto-v1",
        )
        monkeypatch.setattr("canonical.website_enrichment.httpx.get", timeout)

        enrich_business_pool(
            session,
            category="painting",
            market="toronto",
            limit=1,
            page_delay_seconds=0,
            opportunity_policy="weak_or_missing",
            mark_attempted=True,
        )

        observation = session.scalar(
            select(SourceObservationModel).where(SourceObservationModel.source == SOURCE_NAME)
        )
        assert observation is not None
        assert observation.raw_payload["website_enrichment"]["availability_status"] == (
            "inconclusive"
        )
        assert observation.raw_payload["digital_opportunity"]["score"] == 0


def test_website_enrichment_can_target_exact_business_ids(monkeypatch) -> None:
    session_factory = _session_factory()

    with session_factory() as session:
        BusinessSeedService(session).import_seeds(
            [
                painting_seed(
                    company_name="Target Painter",
                    website_url="https://paint.testsite.ca",
                    contact_email=None,
                    contact_name=None,
                    external_id="target-painter",
                ),
                painting_seed(
                    company_name="Other Painter",
                    website_url="https://quiet.example",
                    contact_email=None,
                    contact_name=None,
                    external_id="other-painter",
                ),
            ],
            batch_id="painting-toronto-v1",
        )
        businesses = {
            business.display_name: business
            for business in session.scalars(select(BusinessModel))
        }
        monkeypatch.setattr("canonical.website_enrichment.httpx.get", fake_get)

        summary = enrich_business_pool(
            session,
            category="painting",
            market="toronto",
            limit=2,
            dry_run=False,
            timeout_seconds=0.1,
            page_delay_seconds=0,
            business_ids=[businesses["Target Painter"].id],
        )

        observations = list(
            session.scalars(
                select(SourceObservationModel).where(SourceObservationModel.source == SOURCE_NAME)
            )
        )
        assert summary.selected == 1
        assert [observation.business_id for observation in observations] == [
            businesses["Target Painter"].id
        ]


def test_website_enrichment_ignores_placeholder_email(monkeypatch) -> None:
    session_factory = _session_factory()

    with session_factory() as session:
        BusinessSeedService(session).import_seeds(
            [
                painting_seed(
                    contact_email=None,
                    contact_name=None,
                    website_url="https://placeholder.testsite.ca",
                )
            ],
            batch_id="painting-toronto-v1",
        )

        monkeypatch.setattr("canonical.website_enrichment.httpx.get", fake_placeholder_email_get)

        summary = enrich_business_pool(
            session,
            category="painting",
            market="toronto",
            limit=1,
            dry_run=False,
            timeout_seconds=0.1,
            page_delay_seconds=0,
        )

        assert summary.selected == 1
        assert summary.with_email == 0
        assert summary.written == 1
        assert session.scalar(select(ContactModel).where(ContactModel.email.is_not(None))) is None


def test_cleanup_placeholder_emails_removes_existing_bad_values() -> None:
    session_factory = _session_factory()

    with session_factory() as session:
        BusinessSeedService(session).import_seeds(
            [
                painting_seed(
                    contact_email="your@email.com",
                    contact_name=None,
                    website_url="https://placeholder.testsite.ca",
                )
            ],
            batch_id="painting-toronto-v1",
        )

        summary = cleanup_placeholder_emails(session)

        assert summary["contacts_changed"] == 1
        assert session.scalar(select(ContactModel).where(ContactModel.email == "your@email.com")) is None


class FakeResponse:
    def __init__(self, url: str, text: str) -> None:
        self.url = url
        self.text = text
        self.headers = {"content-type": "text/html"}

    def raise_for_status(self) -> None:
        return None


def fake_get(url: str, **kwargs) -> FakeResponse:
    del kwargs
    pages = {
        "https://paint.testsite.ca": """
            <html>
              <head><title>Paint Example</title></head>
              <body>
                <p>Residential painting in Toronto.</p>
                <a href="/contact">Contact</a>
                <a href="/free-estimate">Free estimate</a>
              </body>
            </html>
        """,
        "https://paint.testsite.ca/contact": """
            <html>
              <head><title>Contact Paint Example</title></head>
              <body>
                Owner: Alex Painter
                Email owner@paint.testsite.ca or call 416-555-0101.
              </body>
            </html>
        """,
        "https://paint.testsite.ca/free-estimate": """
            <html>
              <head><title>Request an Estimate</title></head>
              <body>
                <form><input name="quote" /></form>
                Request a free quote for interior painting and exterior painting.
              </body>
            </html>
        """,
        "https://paint.testsite.ca/contact-us": "<html><body>Contact us.</body></html>",
        "https://paint.testsite.ca/quote": "<html><body>Quote.</body></html>",
        "https://paint.testsite.ca/free-quote": "<html><body>Free quote.</body></html>",
    }
    if url not in pages:
        raise AssertionError(f"Unexpected URL {url}")
    return FakeResponse(url, pages[url])


def fake_no_signal_get(url: str, **kwargs) -> FakeResponse:
    del kwargs
    allowed = {
        "https://quiet.example",
        "https://quiet.example/contact",
        "https://quiet.example/quote",
        "https://quiet.example/free-estimate",
        "https://quiet.example/estimate",
    }
    if url not in allowed:
        raise AssertionError(f"Unexpected URL {url}")
    return FakeResponse(url, "<html><body>Welcome to our local company.</body></html>")


def fake_placeholder_email_get(url: str, **kwargs) -> FakeResponse:
    del kwargs
    allowed = {
        "https://placeholder.testsite.ca",
        "https://placeholder.testsite.ca/contact",
        "https://placeholder.testsite.ca/quote",
        "https://placeholder.testsite.ca/free-estimate",
        "https://placeholder.testsite.ca/estimate",
    }
    if url not in allowed:
        raise AssertionError(f"Unexpected URL {url}")
    return FakeResponse(
        url,
        """
        <html>
          <body>
            Request a free quote for residential painting.
            Email your@email.com for template support.
          </body>
        </html>
        """,
    )


def _session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
