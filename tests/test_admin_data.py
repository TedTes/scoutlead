from datetime import timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from admin.service import AdminDataService
from admin.schemas import AdminBusinessUpdate
from auth.context import AuthContext
from db.models import (
    AdminAuditEventModel,
    BusinessModel,
    BusinessPublicationModel,
    NicheModel,
    ValidationResultModel,
)
from db.session import create_database
from shared.errors import ConflictError
from shared.utils import new_id, utcnow


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
