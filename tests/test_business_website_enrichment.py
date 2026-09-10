from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from db.models import BusinessModel, ContactModel, SourceObservationModel
from db.session import create_database
from scripts.enrich_business_websites import (
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

        monkeypatch.setattr("scripts.enrich_business_websites.httpx.get", fake_get)

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
        assert business.semantic_text
        assert "quote" in business.semantic_text.lower()

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

        monkeypatch.setattr("scripts.enrich_business_websites.httpx.get", fake_get)

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


def test_website_enrichment_can_mark_no_signal_site_as_attempted(monkeypatch) -> None:
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

        monkeypatch.setattr("scripts.enrich_business_websites.httpx.get", fake_no_signal_get)

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

        assert summary.selected == 1
        assert summary.skipped == 1
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
            mark_attempted=True,
            timeout_seconds=0.1,
            page_delay_seconds=0,
        )

        assert second.selected == 0


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

        monkeypatch.setattr("scripts.enrich_business_websites.httpx.get", fake_placeholder_email_get)

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
