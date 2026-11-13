from datetime import timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from admin.schemas import (
    AdminBusinessUpdate,
    AdminDataJobCreate,
    AdminSignalDefinitionCreate,
    AdminSignalDefinitionUpdate,
)
from admin.service import AdminDataService, _admin_match_state
from auth.context import AuthContext
from business_attributes.repository import BusinessAttributeRepository, BusinessAttributeValue
from db.models import (
    AdminAuditEventModel,
    BusinessAttributeModel,
    BusinessIndexSegmentModel,
    BusinessModel,
    BusinessNicheMembershipModel,
    ContactModel,
    NicheModel,
    QueueJobModel,
    SignalDefinitionModel,
    SourceItemModel,
)
from db.session import create_database
from shared.errors import ValidationError
from shared.utils import new_id, utcnow
from source_items.repository import source_item_content_hash
from source_items.schemas import SourceItemCreate


def _session_factory():
    engine = create_engine("sqlite:///:memory:")
    create_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _business(session):
    now = utcnow()
    business = BusinessModel(
        id=new_id("business"),
        display_name="Example Painting",
        normalized_name="example painting",
        geography="Toronto",
        market_key="toronto",
        category_key="home_service_painting",
        status="active",
        first_seen_at=now,
        last_seen_at=now,
    )
    niche = NicheModel(
        id=new_id("niche"),
        slug="home_service_painting",
        label="Painting",
        active=True,
        signal_vocabulary=[],
    )
    session.add_all([business, niche])
    session.commit()
    return business, niche


def _service(session):
    return AdminDataService(
        session,
        AuthContext(user_id="user_admin", email="admin@example.com"),
    )


def _membership(session, business, niche, *, market_key="toronto"):
    now = utcnow()
    membership = BusinessNicheMembershipModel(
        id=new_id("membership"),
        business_id=business.id,
        niche_id=niche.id,
        market_key=market_key,
        confidence=1.0,
        evidence=[],
        first_seen_at=now,
        last_seen_at=now,
    )
    session.add(membership)
    return membership


def _segment(session, niche):
    segment = BusinessIndexSegmentModel(
        id=new_id("segment"),
        niche_id=niche.id,
        market_key="toronto",
        market_label="Toronto",
        status="active",
        demand_count=1,
        target_business_count=25,
        source_plan=[{"provider_id": "google_places", "query": "painters Toronto"}],
        source_state={},
        next_refresh_at=utcnow(),
    )
    session.add(segment)
    session.commit()
    return segment


def _add_attribute(
    session,
    business,
    *,
    key,
    value,
    source="google_places",
    confidence=95,
    definition=None,
    expires_at=None,
):
    now = utcnow()
    attribute = BusinessAttributeRepository(session).upsert(
        business.id,
        BusinessAttributeValue(
            key=key,
            value=value,
            observed_at=now,
            confidence=confidence,
            source_provider=source,
            source_external_id=f"external-{business.id}",
            evidence_hash=new_id("hash")[:64].ljust(64, "0"),
            source_url=f"https://source.example/{business.id}",
            evidence={key: value},
            expires_at=expires_at or now + timedelta(days=30),
        ),
    )
    if definition is not None:
        attribute.signal_definition_id = definition.id
    return attribute, attribute


def test_admin_match_state_uses_eligibility_and_attribute_evidence() -> None:
    definition = SignalDefinitionModel(key="website_status")

    def assessment(eligibility: str, opportunity: str) -> dict:
        return {
            "eligibility": {"state": eligibility},
            "selected_opportunity": {"state": opportunity},
        }

    assert _admin_match_state(assessment("target", "gap"), definition) == "matched"
    assert _admin_match_state(assessment("target", "review"), definition) == "not_evaluated"
    assert _admin_match_state(assessment("target", "healthy"), definition) == "does_not_match"
    assert _admin_match_state(assessment("excluded", "gap"), definition) == "not_qualified"


def test_admin_detail_uses_selected_trade_and_market_without_validation_rows() -> None:
    factory = _session_factory()
    with factory() as session:
        business, painting = _business(session)
        electrical = NicheModel(
            id=new_id("niche"),
            slug="home_service_electrical",
            label="Electrical",
            active=True,
            signal_vocabulary=[],
        )
        session.add(electrical)
        _membership(session, business, painting)
        _membership(session, business, electrical)
        _membership(session, business, electrical, market_key="north york")
        session.commit()

        detail = _service(session).detail(
            business.id,
            niche_slug=electrical.slug,
            market_key="toronto",
        )

        assert detail["niche_slug"] == electrical.slug
        assert detail["market_key"] == "toronto"
        assert detail["eligibility_state"] == "target"


def test_admin_business_detail_includes_contacts() -> None:
    factory = _session_factory()
    with factory() as session:
        business, _ = _business(session)
        now = utcnow()
        session.add(
            ContactModel(
                id=new_id("contact"),
                business_id=business.id,
                name="Alex Owner",
                role="Owner",
                email="alex@example.test",
                phone="4165550100",
                verification_status="verified",
                verification_provider="test",
                verification_checked_at=now,
                verification_score=98,
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        session.commit()

        detail = _service(session).detail(business.id)

        assert detail["contacts"][0]["name"] == "Alex Owner"
        assert detail["contacts"][0]["verification_status"] == "verified"


def test_admin_business_json_includes_attribute_and_embedded_evidence() -> None:
    factory = _session_factory()
    with factory() as session:
        business, _ = _business(session)
        evidence, _ = _add_attribute(
            session,
            business,
            key="business_operational",
            value=True,
        )
        session.commit()

        payload = _service(session).business_json(business.id)
        exported = _service(session).export_businesses_json([business.id, business.id])

        assert payload["business"]["id"] == business.id
        attribute = payload["attributes"]["business_operational"]
        assert attribute["value"] is True
        assert attribute["source"]["provider"] == "google_places"
        assert payload["evidence"]["records"][0]["id"] == evidence.id
        assert payload["evidence"]["records"][0]["payload"] == {
            "business_operational": True
        }
        assert exported["business_count"] == 1


def test_admin_lists_business_with_attributes_as_evaluated_and_searchable() -> None:
    factory = _session_factory()
    with factory() as session:
        business, niche = _business(session)
        _membership(session, business, niche)
        _add_attribute(session, business, key="business_operational", value=True)
        session.commit()

        overview = _service(session).overview()
        rows = _service(session).list_businesses(
            query=None,
            validation=None,
            quality=None,
            sort="name",
            status=None,
            niche_slug=niche.slug,
            market_key=None,
            page=1,
            page_size=50,
        )["items"]

        assert overview["searchable"] == 1
        assert overview["fully_validated"] == 1
        assert rows[0]["evaluation_state"] == "evaluated"


def test_admin_attribute_match_reads_canonical_attribute_directly() -> None:
    factory = _session_factory()
    with factory() as session:
        missing_website, niche = _business(session)
        now = utcnow()
        has_form = BusinessModel(
            id=new_id("business"),
            display_name="Has Form Painting",
            normalized_name="has form painting",
            geography="Toronto",
            market_key="toronto",
            category_key=niche.slug,
            status="active",
            first_seen_at=now,
            last_seen_at=now,
        )
        definition = SignalDefinitionModel(
            id=new_id("signal"),
            key="website_status",
            label="Website status",
            value_type="text",
            category="website",
            status="active",
            collector_key="website_presence",
            extractor_key="website_status",
            freshness_days=30,
            opportunity_direction="missing_is_opportunity",
            config={
                "minimum_confidence": 90,
                "opportunity_values": ["missing"],
                "audience_min_score": 50,
            },
            version=1,
        )
        session.add_all([has_form, definition])
        session.flush()
        for business, status in ((missing_website, "missing"), (has_form, "present")):
            _membership(session, business, niche)
            _add_attribute(
                session,
                business,
                key=definition.key,
                value=status,
                definition=definition,
            )
        session.commit()

        result = _service(session).list_businesses(
            query=None,
            validation=None,
            quality=None,
            sort="name",
            status=None,
            niche_slug=None,
            market_key=None,
            page=1,
            page_size=50,
            match_attribute="website_status",
        )
        all_states = _service(session).list_businesses(
            query=None,
            validation=None,
            quality=None,
            sort="name",
            status=None,
            niche_slug=None,
            market_key=None,
            page=1,
            page_size=50,
            match_attribute="website_status",
            match_state="all",
        )

        assert [row["id"] for row in result["items"]] == [missing_website.id]
        assert {row["id"]: row["match_state"] for row in all_states["items"]} == {
            missing_website.id: "matched",
            has_form.id: "does_not_match",
        }


def test_attribute_lineage_connects_canonical_value_to_evidence() -> None:
    factory = _session_factory()
    with factory() as session:
        business, _ = _business(session)
        definition = SignalDefinitionModel(
            id=new_id("signal"),
            key="website_status",
            label="Website status",
            value_type="text",
            category="website",
            status="active",
            collector_key="website_presence",
            extractor_key="website_status",
            freshness_days=30,
            opportunity_direction="missing_is_opportunity",
            config={
                "minimum_confidence": 90,
                "opportunity_values": ["missing"],
            },
            version=1,
        )
        session.add(definition)
        session.flush()
        evidence, attribute = _add_attribute(
            session,
            business,
            key=definition.key,
            value="missing",
            source="company_website_signal",
            definition=definition,
        )
        session.commit()

        result = _service(session).attribute_lineage(business.id)

        assert result["business_id"] == business.id
        lineage_attribute = next(
            item for item in result["attributes"] if item["id"] == attribute.id
        )
        assert lineage_attribute["source_evidence_id"] == evidence.id
        assert lineage_attribute["signal"]["eligible_for_matching"] is True
        assert result["evidence_records"][0]["payload"] == {
            "website_status": "missing"
        }


def test_delete_business_purges_attributes_and_retains_audit() -> None:
    factory = _session_factory()
    with factory() as session:
        business, niche = _business(session)
        _membership(session, business, niche)
        _add_attribute(session, business, key="business_operational", value=True)
        session.commit()

        service = _service(session)
        dependencies = service.delete_dependencies(business.id)
        assert dependencies["business_attributes"] == 1

        service.delete(
            business.id,
            business.display_name,
            "Confirmed false business record",
        )

        assert session.get(BusinessModel, business.id) is None
        assert session.scalar(
            select(BusinessAttributeModel).where(
                BusinessAttributeModel.business_id == business.id
            )
        ) is None
        audit = session.scalar(
            select(AdminAuditEventModel).where(
                AdminAuditEventModel.entity_id == business.id,
                AdminAuditEventModel.action == "delete",
            )
        )
        assert audit.after["deleted_dependencies"]["business_attributes"] == 1


def test_edit_quarantines_business_and_audits() -> None:
    factory = _session_factory()
    with factory() as session:
        business, _ = _business(session)

        result = _service(session).update(
            business.id,
            AdminBusinessUpdate(
                phone="4165550199",
                reason="Corrected from source profile",
            ),
        )

        audit = session.scalar(select(AdminAuditEventModel))
        assert result["status"] == "quarantined"
        assert audit.action == "update"
        assert audit.after["phone"] == "4165550199"


def test_admin_recheck_creates_fresh_source_item_without_validation_table() -> None:
    factory = _session_factory()
    with factory() as session:
        business, niche = _business(session)
        segment = _segment(session, niche)
        source_value = SourceItemCreate(
            segment_id=segment.id,
            provider_id="google_places",
            external_id="place-example",
            query="painters Toronto",
            source_url="https://maps.example/example-painting",
            title="Example Painting",
            raw_payload={"primaryTypeDisplayName": "Painter"},
            fetched_at=utcnow(),
        )
        source = SourceItemModel(
            id=new_id("source_item"),
            **source_value.model_dump(),
            content_hash=source_item_content_hash(source_value),
            state="eligible",
            business_id=business.id,
        )
        session.add(source)
        session.commit()

        result = _service(session).revalidate(
            business.id,
            "Refresh source evidence",
        )

        assert result["validation_state"] in {"passed", "incomplete"}
        assert session.scalar(select(QueueJobModel)) is None
        assert len(
            list(
                session.scalars(
                    select(SourceItemModel).where(
                        SourceItemModel.business_id == business.id
                    )
                )
            )
        ) == 2


def test_admin_can_queue_review_first_data_job() -> None:
    factory = _session_factory()
    with factory() as session:
        _, niche = _business(session)
        segment = _segment(session, niche)

        result = _service(session).create_data_job(
            AdminDataJobCreate(
                segment_id=segment.id,
                processing_mode="review_first",
                reason="Inspect a new source batch",
            )
        )

        job = session.get(QueueJobModel, result["id"])
        assert job.payload["processing_mode"] == "review_first"


def test_admin_can_create_update_and_activate_attribute_definition() -> None:
    factory = _session_factory()
    with factory() as session:
        service = _service(session)
        created = service.create_signal_definition(
            AdminSignalDefinitionCreate(
                key="primary_cta_present",
                label="Primary CTA present",
                value_type="boolean",
                category="conversion",
                collector_key="website_dom",
                extractor_key="primary_cta",
                freshness_days=30,
                opportunity_direction="false_is_opportunity",
                reason="Add a measurable business attribute",
            )
        )
        updated = service.update_signal_definition(
            created["id"],
            AdminSignalDefinitionUpdate(
                description="A visible primary action is available.",
                reason="Clarify the attribute definition",
            ),
        )
        activated = service.change_signal_definition_status(
            created["id"],
            status="active",
            reason="Ready for collection",
        )

        assert created["status"] == "draft"
        assert updated["version"] == 2
        assert activated["status"] == "active"


def test_definition_without_collector_cannot_be_activated() -> None:
    factory = _session_factory()
    with factory() as session:
        created = _service(session).create_signal_definition(
            AdminSignalDefinitionCreate(
                key="manual_quality_note",
                label="Manual quality note",
                value_type="text",
                category="quality",
                reason="Prepare a manual attribute",
            )
        )

        with pytest.raises(ValidationError):
            _service(session).change_signal_definition_status(
                created["id"],
                status="active",
                reason="Attempt activation",
            )
