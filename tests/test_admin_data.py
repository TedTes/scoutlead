from datetime import timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from admin.service import AdminDataService
from admin.schemas import AdminBusinessUpdate, AdminDataJobCreate
from auth.context import AuthContext
from db.models import (
    AdminAuditEventModel,
    BusinessModel,
    BusinessIndexSegmentModel,
    BusinessPublicationModel,
    NicheModel,
    ProductModel,
    QueueJobModel,
    SourceItemModel,
    ValidationResultModel,
)
from db.session import create_database
from shared.errors import ConflictError
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


def _segment(session, niche):
    product = ProductModel(
        id=new_id("product"),
        workspace_id=None,
        product_name="Website growth",
        product_description=None,
        target_customer="Local service businesses",
        problem_being_solved=None,
        value_proposition=None,
        target_geography="Toronto",
        validation_goal=None,
        qualification_criteria=[],
        preferred_discovery_sources=[],
        outreach_objective=None,
        constraints=[],
        offer_summary=None,
        ideal_customer_signals=[],
        exclusions=[],
        typical_deal_value=None,
    )
    segment = BusinessIndexSegmentModel(
        id=new_id("segment"),
        niche_id=niche.id,
        product_id=product.id,
        market_key="toronto",
        market_label="Toronto",
        status="active",
        demand_count=1,
        target_business_count=25,
        source_plan=[{"provider_id": "google_places", "query": "painters Toronto"}],
        source_state={},
        next_refresh_at=utcnow(),
    )
    session.add_all([product, segment])
    session.commit()
    return segment


def test_edit_quarantines_business_withdraws_publication_and_audits() -> None:
    factory = _session_factory()
    with factory() as session:
        business, niche = _business(session)
        session.add(
            BusinessPublicationModel(
                id=new_id("publication"),
                business_id=business.id,
                niche_id=niche.id,
                market_key="toronto",
                status="published",
                policy_version=1,
                reasons=[],
                evaluated_at=utcnow(),
            )
        )
        session.commit()

        result = _service(session).update(
            business.id,
            AdminBusinessUpdate(phone="4165550199", reason="Corrected from source profile"),
        )

        publication = session.scalar(select(BusinessPublicationModel))
        audit = session.scalar(select(AdminAuditEventModel))
        assert result["status"] == "quarantined"
        assert publication.status == "quarantined"
        assert audit.action == "update"
        assert audit.actor_email == "admin@example.com"
        assert audit.before["phone"] is None
        assert audit.after["phone"] == "4165550199"


def test_expired_validation_is_reported_as_incomplete() -> None:
    factory = _session_factory()
    with factory() as session:
        business, _ = _business(session)
        now = utcnow()
        for validation_type in ("identity", "business_identity", "trade", "location"):
            session.add(
                ValidationResultModel(
                    id=new_id("validation"),
                    idempotency_key=f"{business.id}:{validation_type}",
                    business_id=business.id,
                    validation_type=validation_type,
                    status="passed",
                    confidence=95,
                    reason="Passed",
                    evidence=[],
                    validator="test",
                    validator_version=1,
                    observed_at=now - timedelta(days=40),
                    expires_at=now - timedelta(days=10),
                )
            )
        session.commit()

        overview = _service(session).overview()

        assert overview["fully_validated"] == 0
        assert overview["incomplete"] == 1


def test_permanent_delete_is_blocked_when_related_records_exist() -> None:
    factory = _session_factory()
    with factory() as session:
        business, niche = _business(session)
        session.add(
            BusinessPublicationModel(
                id=new_id("publication"),
                business_id=business.id,
                niche_id=niche.id,
                market_key="toronto",
                status="staged",
                policy_version=1,
                reasons=[],
                evaluated_at=utcnow(),
            )
        )
        session.commit()

        with pytest.raises(ConflictError):
            _service(session).delete(
                business.id,
                confirmation=business.display_name,
                reason="Duplicate record",
            )


def test_admin_can_queue_review_first_data_job() -> None:
    factory = _session_factory()
    with factory() as session:
        _, niche = _business(session)
        segment = _segment(session, niche)

        result = _service(session).create_data_job(
            AdminDataJobCreate(
                segment_id=segment.id,
                processing_mode="review_first",
                reason="Inspect a new source batch before validation",
            )
        )

        job = session.get(QueueJobModel, result["id"])
        assert result["status"] == "queued"
        assert job is not None
        assert job.payload["admin_requested"] is True
        assert job.payload["processing_mode"] == "review_first"
        assert session.scalar(
            select(AdminAuditEventModel).where(
                AdminAuditEventModel.entity_type == "data_job"
            )
        ).action == "data_job:create"


def test_review_first_batch_only_enters_pipeline_after_admin_approval() -> None:
    factory = _session_factory()
    with factory() as session:
        _, niche = _business(session)
        segment = _segment(session, niche)
        service = _service(session)
        root_summary = service.create_data_job(
            AdminDataJobCreate(
                segment_id=segment.id,
                processing_mode="review_first",
                reason="Review before validation",
            )
        )
        root = session.get(QueueJobModel, root_summary["id"])
        root.status = "completed"
        root.completed_at = utcnow()
        child = QueueJobModel(
            id=new_id("job"),
            type="source.fetch",
            payload={
                "segment_id": segment.id,
                "source_index": 0,
                "processing_mode": "review_first",
            },
            status="completed",
            attempts=1,
            max_attempts=3,
            run_after=utcnow(),
            parent_run_id=root.id,
            completed_at=utcnow(),
        )
        session.add(child)
        session.flush()
        source_value = SourceItemCreate(
            segment_id=segment.id,
            job_id=child.id,
            provider_id="google_places",
            external_id="place-1",
            query="painters Toronto",
            source_url="https://maps.example/place-1",
            title="Example Painter",
            raw_payload={"address": "Toronto", "phone": "4165550100"},
            fetched_at=utcnow(),
        )
        source = SourceItemModel(
            id=new_id("source_item"),
            **source_value.model_dump(),
            content_hash=source_item_content_hash(source_value),
            state="fetched",
        )
        session.add(source)
        session.commit()

        before = service.data_job_detail(root.id)
        assert before["status"] == "awaiting_review"
        assert before["pending_review"] == 1
        assert source.business_id is None

        after = service.validate_data_job(
            root.id,
            reason="The source sample has sufficient identity fields",
            source_item_ids=[source.id],
        )

        queued = session.scalar(
            select(QueueJobModel).where(QueueJobModel.type == "source_item.classify")
        )
        assert queued is not None
        assert queued.payload["source_item_id"] == source.id
        assert source.business_id is None
        assert source.state == "validation_queued"
        assert after["review_state"] == "approved"
