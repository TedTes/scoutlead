from importlib import import_module

import sqlalchemy as sa
from sqlalchemy.orm import Session

from db.models import (
    BusinessFactModel,
    BusinessModel,
    ServiceDefinitionModel,
    ServiceSignalMappingModel,
    SignalDefinitionModel,
    SourceObservationModel,
)
from db.session import create_database
from shared.utils import utcnow


def test_attribute_catalog_backfills_only_observed_business_values(monkeypatch) -> None:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    create_database(engine)
    now = utcnow()
    with Session(engine) as session:
        session.add(
            ServiceDefinitionModel(
                id="service_lead_capture",
                key="lead_capture",
                label="Lead capture",
                status="active",
                sort_order=1,
                version=1,
            )
        )
        session.add(
            BusinessModel(
                id="business_attribute_backfill",
                display_name="Attribute Backfill Painter",
                normalized_name="attribute backfill painter",
                website_url="https://backfill.example",
                domain="backfill.example",
                phone="4165550101",
                address="10 King St, Toronto, ON M5V 1A1",
                market_key="toronto",
                latitude=43.65,
                longitude=-79.38,
                is_directory=False,
                customer_kind="unknown",
                status="active",
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        session.flush()
        session.add(
            SourceObservationModel(
                id="observation_attribute_backfill",
                business_id="business_attribute_backfill",
                source="google_places",
                external_id="places/backfill",
                content_hash="attribute-backfill",
                raw_payload={
                    "id": "places/backfill",
                    "city": "Toronto",
                    "province": "Ontario",
                    "postal_code": "M5V 1A1",
                },
                observed_at=now,
            )
        )
        session.commit()

    migration = import_module(
        "db.migrations.versions.20261101_0066_complete_business_attribute_catalog"
    )
    with engine.begin() as connection:
        monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
        migration.upgrade()

    with Session(engine) as session:
        facts = {
            fact.fact_key: fact
            for fact in session.scalars(
                sa.select(BusinessFactModel).where(
                    BusinessFactModel.business_id == "business_attribute_backfill"
                )
            )
        }
        assert facts["business_name"].attribute_score == 0
        assert facts["website_url"].attribute_score == 0
        assert facts["city"].value_text == "Toronto"
        assert facts["google_business_profile_present"].value_boolean is True
        assert "is_chain" not in facts
        mapped_attributes = set(
            session.scalars(
                sa.select(SignalDefinitionModel.key)
                .join(
                    ServiceSignalMappingModel,
                    ServiceSignalMappingModel.signal_definition_id
                    == SignalDefinitionModel.id,
                )
                .where(
                    ServiceSignalMappingModel.service_definition_id
                    == "service_lead_capture"
                )
            )
        )
        assert mapped_attributes == {
            "contact_form_present",
            "primary_cta_present",
            "click_to_call_present",
            "public_email_present",
            "public_phone_present",
        }
        catalog_keys = set(session.scalars(sa.select(SignalDefinitionModel.key)))
        assert {
            "business_name",
            "business_operational",
            "trade_category",
            "provider_business_id",
            "address",
            "city",
            "region",
            "postal_code",
            "latitude",
            "longitude",
            "phone",
            "website_url",
            "domain",
            "is_directory",
            "is_chain",
            "is_franchise",
            "website_status",
            "website_ownership",
            "http_status",
            "uses_https",
            "mobile_viewport_present",
            "website_quality_score",
            "performance_score",
            "accessibility_score",
            "best_practices_score",
            "contact_form_present",
            "contact_page_url",
            "quote_or_booking_form_present",
            "booking_url",
            "primary_cta_present",
            "click_to_call_present",
            "public_email_present",
            "public_phone_present",
            "google_rating",
            "google_review_count",
            "review_recency_days",
            "google_business_profile_present",
            "local_business_schema_present",
            "service_area_content_present",
            "title_and_meta_present",
            "verified_email",
            "verified_phone",
            "contact_form_url",
            "preferred_contact_channel",
        }.issubset(catalog_keys)

