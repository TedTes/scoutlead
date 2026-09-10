from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from db.models import BusinessModel, SourceObservationModel
from db.session import create_database
from shared.utils import new_id, utcnow
from scripts.audit_business_pool import build_audit
from seeding.service import BusinessSeedService
from tests.test_business_seeding import FakeEmbeddingClient, painting_seed


def test_business_pool_audit_reports_filtered_readiness() -> None:
    session_factory = _session_factory()

    with session_factory() as session:
        BusinessSeedService(session, embedding=FakeEmbeddingClient()).import_seeds(
            [
                painting_seed(),
                painting_seed(
                    company_name="No Email Painter",
                    website_url="https://no-email-painter.test",
                    phone="647-555-0199",
                    contact_email=None,
                    contact_name=None,
                    geography="Mississauga, ON",
                    address="55 Seed Rd, Mississauga, ON",
                ),
            ],
            batch_id="painting-toronto-v1",
        )

        audit = build_audit(session, category="painting", market="toronto")

    assert audit["businesses"]["total"] == 2
    assert audit["businesses"]["with_website"] == 2
    assert audit["businesses"]["with_phone"] == 2
    assert audit["businesses"]["with_embedding"] == 2
    assert audit["businesses"]["with_quote_or_estimate_signal"] == 2
    assert audit["contacts"]["businesses_with_email"] == 1
    assert audit["contacts"]["businesses_with_phone_or_email"] == 2
    assert audit["sources"]["by_source"] == {"manual_seed": 2}
    assert audit["sources"]["by_seed_batch"] == {"painting-toronto-v1": 2}
    assert audit["taxonomy"]["by_category"] == {"home service painting providers": 2}
    assert audit["taxonomy"]["by_market"] == {"toronto gta": 2}


def test_business_pool_audit_handles_empty_pool() -> None:
    session_factory = _session_factory()

    with session_factory() as session:
        audit = build_audit(session, category="painting", market="toronto")

    assert audit["businesses"]["total"] == 0
    assert audit["contacts"]["total"] == 0
    assert audit["sources"]["observations"] == 0


def test_business_pool_audit_does_not_count_website_quote_urls_as_quote_signal() -> None:
    session_factory = _session_factory()

    with session_factory() as session:
        BusinessSeedService(session, embedding=FakeEmbeddingClient()).import_seeds(
            [
                painting_seed(
                    company_name="Quiet Painter",
                    website_url="https://quiet-painter.test",
                    contact_email=None,
                    contact_name=None,
                    description="Residential painter serving Toronto homes.",
                    query="residential painter Toronto",
                    signals=["residential painting"],
                )
            ],
            batch_id="painting-toronto-v1",
        )
        business = session.scalar(select(BusinessModel))
        assert business is not None
        session.add(
            SourceObservationModel(
                id=new_id("sourceobs"),
                business_id=business.id,
                source="company_website_seed",
                external_id=f"website_enrichment:{business.id}",
                query_signature=None,
                content_hash="website-quote-url-only",
                source_url="https://quiet-painter.test",
                raw_payload={
                    "description": "Quiet Painter website enrichment found public website evidence.",
                    "website_enrichment": {
                        "inspected_urls": [
                            "https://quiet-painter.test",
                            "https://quiet-painter.test/quote",
                        ],
                        "quote_signals": [],
                        "has_quote_form": False,
                    },
                },
                observed_at=utcnow(),
            )
        )
        session.commit()

        audit = build_audit(session, category="painting", market="toronto")

    assert audit["businesses"]["with_quote_or_estimate_signal"] == 0


def _session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
