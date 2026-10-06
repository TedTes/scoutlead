from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import BusinessModel, BusinessNicheMembershipModel, NicheModel
from db.session import create_database
from scripts.refine_trade_memberships import find_invalid_memberships
from shared.utils import utcnow


def test_cleanup_only_reports_unsupported_lexical_trade_memberships() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        now = utcnow()
        hvac = NicheModel(
            id="niche_hvac",
            slug="home_service_hvac",
            label="HVAC",
            category="home services",
            active=True,
        )
        session.add(hvac)
        for business_id, name in (
            ("wrong", "Painting Company"),
            ("valid", "Heating Company"),
            ("explicit", "Explicit HVAC Company"),
        ):
            session.add(
                BusinessModel(
                    id=business_id,
                    display_name=name,
                    normalized_name=name.lower(),
                    status="active",
                    customer_kind="residential",
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
        session.flush()
        session.add_all(
            [
                _membership("bad", "wrong", "residential painting contractors Toronto", now),
                _membership("good", "valid", "heating and cooling Toronto", now),
                _membership(
                    "explicit-membership",
                    "explicit",
                    "local services Toronto",
                    now,
                    resolution_type="explicit",
                ),
            ]
        )
        session.commit()

        invalid = find_invalid_memberships(session)

        assert [item.membership_id for item in invalid] == ["bad"]
        assert invalid[0].business_name == "Painting Company"


def _membership(
    membership_id: str,
    business_id: str,
    query: str,
    now,
    *,
    resolution_type: str = "lexical",
) -> BusinessNicheMembershipModel:
    return BusinessNicheMembershipModel(
        id=membership_id,
        business_id=business_id,
        niche_id="niche_hvac",
        market_key="toronto",
        confidence=0.5,
        evidence=[
            {
                "type": "discovery_association",
                "query": query,
                "resolution_type": resolution_type,
            }
        ],
        first_seen_at=now,
        last_seen_at=now,
    )
