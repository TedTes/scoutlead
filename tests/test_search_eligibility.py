from datetime import timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from business_index.eligibility import searchable_business_conditions
from db.models import BusinessAttributeModel, BusinessModel, BusinessNicheMembershipModel, NicheModel
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
    return business, now


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


def _add_operational_attribute(session, business, observed_at, value: bool) -> None:
    payload = {"businessStatus": "OPERATIONAL" if value else "CLOSED_PERMANENTLY"}
    session.add(
        BusinessAttributeModel(
            id=new_id("business_attribute"),
            business_id=business.id,
            attribute_key="business_operational",
            value_type="boolean",
            value_boolean=value,
            confidence=100,
            attribute_score=100,
            observed_at=observed_at,
            expires_at=observed_at + timedelta(days=90),
            source="google_places",
            evidence_hash="a" * 64,
            source_external_id=f"place-{business.id}",
            source_url=f"https://maps.example/{business.id}",
            evidence=payload,
        )
    )
    session.commit()


def test_active_business_membership_is_searchable_without_validation_log() -> None:
    factory = _session_factory()
    with factory() as session:
        business, _ = _eligible_scope(session)
        assert _searchable_ids(session) == [business.id]


def test_unknown_operational_status_does_not_block_search() -> None:
    factory = _session_factory()
    with factory() as session:
        business, _ = _eligible_scope(session)
        assert _searchable_ids(session) == [business.id]


def test_confirmed_inactive_attribute_blocks_search() -> None:
    factory = _session_factory()
    with factory() as session:
        business, observed_at = _eligible_scope(session)
        _add_operational_attribute(session, business, observed_at, False)
        assert _searchable_ids(session) == []


def test_expired_inactive_attribute_does_not_block_search() -> None:
    factory = _session_factory()
    with factory() as session:
        business, _ = _eligible_scope(session)
        _add_operational_attribute(session, business, utcnow() - timedelta(days=120), False)
        assert _searchable_ids(session) == [business.id]


def test_closed_business_is_not_searchable() -> None:
    factory = _session_factory()
    with factory() as session:
        business, _ = _eligible_scope(session)
        business.status = "closed"
        session.commit()
        assert _searchable_ids(session) == []
