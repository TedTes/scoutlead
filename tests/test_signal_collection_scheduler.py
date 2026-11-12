from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from db.models import (
    BusinessModel,
    BusinessNicheMembershipModel,
    NicheModel,
    QueueJobModel,
    SignalDefinitionModel,
)
from db.session import create_database
from shared.utils import new_id, utcnow
from signal_collection.requirements import STANDING_WEBSITE_ATTRIBUTE_KEYS
from signal_collection.scheduler import enqueue_due_signal_collections


def test_standing_refresh_queues_missing_website_evidence() -> None:
    engine = create_engine("sqlite:///:memory:")
    create_database(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        now = utcnow()
        niche = NicheModel(
            id=new_id("niche"),
            slug="painters",
            label="Painters",
            category="Home services",
            active=True,
            signal_vocabulary=[],
        )
        business = BusinessModel(
            id=new_id("business"),
            display_name="Example Painting",
            normalized_name="example painting",
            website_url="https://example.test",
            status="active",
            first_seen_at=now,
            last_seen_at=now,
        )
        definition = SignalDefinitionModel(
            id=new_id("signal"),
            key="website_quality_score",
            label="Website quality score",
            value_type="number",
            category="website",
            status="active",
            collector_key="pagespeed_mobile",
            extractor_key="payload_path",
            freshness_days=14,
            opportunity_direction="below_threshold",
            config={"payload_path": "pagespeed_mobile.website_quality_score"},
            version=1,
        )
        session.add_all([niche, business, definition])
        session.flush()
        session.add(
            BusinessNicheMembershipModel(
                id=new_id("membership"),
                business_id=business.id,
                niche_id=niche.id,
                market_key="toronto",
                confidence=1.0,
                evidence=[],
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        session.commit()

        queued = enqueue_due_signal_collections(session, limit=50, batch_size=10)

        assert queued == 1
        job = session.scalar(select(QueueJobModel))
        assert job is not None
        assert job.type == "signal.collection"
        assert job.payload["signal_definition_id"] == definition.id
        assert job.payload["business_ids"] == [business.id]
        assert job.payload["reason"] == "scheduled_website_evidence_refresh"


def test_standing_website_collection_covers_composite_upgrade_components() -> None:
    assert STANDING_WEBSITE_ATTRIBUTE_KEYS == {
        "website_status",
        "website_quality_score",
        "mobile_viewport_present",
        "contact_form_present",
        "quote_or_booking_form_present",
        "primary_cta_present",
        "click_to_call_present",
    }
