from datetime import timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from business_index.eligibility import REQUIRED_VALIDATIONS, searchable_business_conditions
from db.models import (
    BusinessModel,
    BusinessNicheMembershipModel,
    NicheModel,
    ValidationResultModel,
)
from db.session import create_database
from shared.utils import new_id, utcnow


def _session_factory():
    engine = create_engine("sqlite:///:memory:")
    create_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _eligible_scope(session):
    now = utcnow()
    business = BusinessModel(
        id=new_id("business"),
        display_name="Example HVAC",
        normalized_name="example hvac",
        market_key="toronto",
        status="active",
        first_seen_at=now,
        last_seen_at=now,
    )
    niche = NicheModel(
        id=new_id("niche"),
        slug="home_service_hvac",
        label="HVAC",
        active=True,
        signal_vocabulary=[],
    )
    session.add_all([business, niche])
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
    for dimension, confidence in REQUIRED_VALIDATIONS.items():
        session.add(
            ValidationResultModel(
                id=new_id("validation"),
                idempotency_key=f"{business.id}:{dimension}:passed",
                business_id=business.id,
                niche_id=niche.id,
                market_key="toronto",
                validation_type=dimension,
                status="passed",
                confidence=confidence,
                reason="Passed",
                evidence=[],
                validator="test",
                validator_version=1,
                observed_at=now,
                expires_at=now + timedelta(days=30),
            )
        )
    session.commit()
    return business, niche, now


def _searchable_ids(session) -> list[str]:
    return list(
        session.scalars(
            select(BusinessModel.id)
            .join(
                BusinessNicheMembershipModel,
                BusinessNicheMembershipModel.business_id == BusinessModel.id,
            )
            .where(*searchable_business_conditions())
        )
    )


def test_current_passed_validations_make_membership_searchable() -> None:
    factory = _session_factory()
    with factory() as session:
        business, _, _ = _eligible_scope(session)

        assert _searchable_ids(session) == [business.id]


def test_newer_failed_validation_removes_membership_from_search() -> None:
    factory = _session_factory()
    with factory() as session:
        business, niche, observed_at = _eligible_scope(session)
        session.add(
            ValidationResultModel(
                id=new_id("validation"),
                idempotency_key=f"{business.id}:trade:failed",
                business_id=business.id,
                niche_id=niche.id,
                market_key="toronto",
                validation_type="trade",
                status="failed",
                confidence=95,
                reason="Wrong trade",
                evidence=[],
                validator="test",
                validator_version=1,
                observed_at=observed_at + timedelta(seconds=1),
                expires_at=observed_at + timedelta(days=30),
            )
        )
        session.commit()

        assert _searchable_ids(session) == []
