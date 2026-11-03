from datetime import timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from business_index.eligibility import searchable_business_conditions
from db.models import (
    BusinessFactModel,
    BusinessModel,
    BusinessNicheMembershipModel,
    NicheModel,
    SourceObservationModel,
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


def _add_passed_validations(
    session,
    business,
    niche,
    observed_at,
    *,
    operational: bool | None = True,
) -> None:
    for validation_type, confidence in {
        "identity": 90,
        "business_identity": 85,
        "trade": 90,
        "location": 85,
    }.items():
        session.add(
            ValidationResultModel(
                id=new_id("validation"),
                idempotency_key=f"{business.id}:{validation_type}:passed",
                business_id=business.id,
                niche_id=niche.id,
                market_key="toronto",
                validation_type=validation_type,
                status="passed",
                confidence=confidence,
                reason="Current validation passed.",
                evidence=[],
                validator="test",
                validator_version=1,
                observed_at=observed_at,
                expires_at=observed_at + timedelta(days=30),
            )
        )
    if operational is None:
        session.commit()
        return
    observation = SourceObservationModel(
        id=new_id("observation"),
        business_id=business.id,
        source="google_places",
        external_id=f"place-{business.id}",
        query_signature=None,
        content_hash="a" * 64,
        source_url=f"https://maps.example/{business.id}",
        raw_payload={
            "businessStatus": "OPERATIONAL" if operational else "CLOSED_PERMANENTLY"
        },
        observed_at=observed_at,
    )
    session.add(observation)
    session.flush()
    session.add(
        BusinessFactModel(
            id=new_id("fact"),
            business_id=business.id,
            fact_key="business_operational",
            value_type="boolean",
            value_boolean=operational,
            confidence=100,
            attribute_score=100,
            score_version=1,
            score_reason="present",
            resolution_state="confirmed",
            supporting_claim_ids=[],
            quality_state="published",
            quality_policy_version=1,
            observed_at=observed_at,
            expires_at=observed_at + timedelta(days=90),
            source_observation_id=observation.id,
            resolver_version=1,
        )
    )
    session.commit()


def test_active_business_membership_is_not_searchable_without_validations() -> None:
    factory = _session_factory()
    with factory() as session:
        _eligible_scope(session)

        assert _searchable_ids(session) == []


def test_active_business_membership_is_searchable_with_current_validations() -> None:
    factory = _session_factory()
    with factory() as session:
        business, niche, observed_at = _eligible_scope(session)
        _add_passed_validations(session, business, niche, observed_at)

        assert _searchable_ids(session) == [business.id]


def test_unverified_operational_status_does_not_block_search() -> None:
    factory = _session_factory()
    with factory() as session:
        business, niche, observed_at = _eligible_scope(session)
        _add_passed_validations(
            session,
            business,
            niche,
            observed_at,
            operational=None,
        )

        assert _searchable_ids(session) == [business.id]


def test_confirmed_inactive_business_is_not_searchable() -> None:
    factory = _session_factory()
    with factory() as session:
        business, niche, observed_at = _eligible_scope(session)
        _add_passed_validations(
            session,
            business,
            niche,
            observed_at,
            operational=False,
        )

        assert _searchable_ids(session) == []


def test_failed_quality_validation_does_not_remove_membership_from_search() -> None:
    factory = _session_factory()
    with factory() as session:
        business, niche, observed_at = _eligible_scope(session)
        _add_passed_validations(session, business, niche, observed_at)
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


def test_closed_business_is_not_searchable() -> None:
    factory = _session_factory()
    with factory() as session:
        business, niche, observed_at = _eligible_scope(session)
        _add_passed_validations(session, business, niche, observed_at)
        business.status = "closed"
        session.commit()

        assert _searchable_ids(session) == []
