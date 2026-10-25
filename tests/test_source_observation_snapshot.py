from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from canonical.normalization import stable_content_hash
from canonical.repository import CanonicalRepository
from db.models import SourceObservationModel
from db.session import create_database


def test_observation_payload_is_independent_from_caller_input() -> None:
    engine = create_engine("sqlite:///:memory:")
    create_database(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    raw = {
        "external_id": "place_1",
        "address": "1 Main St, Toronto, ON",
        "details": {"rating": 4.8},
    }

    with factory() as session:
        CanonicalRepository(session).upsert_from_discovery_result(
            company_name="Example Services",
            geography="Toronto, ON",
            source="google_places",
            raw=raw,
        )
        raw["details"]["rating"] = 1.0
        raw["added_later"] = True
        session.commit()

        observation = session.scalar(select(SourceObservationModel))
        assert observation is not None
        assert observation.raw_payload["details"]["rating"] == 4.8
        assert "added_later" not in observation.raw_payload
        assert observation.content_hash == stable_content_hash(observation.raw_payload)
