from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from db.models import NicheModel, WorkspaceModel
from db.session import create_database
from niches.seeding import load_trade_catalog, seed_trade_catalog


CATALOG_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "seeds"
    / "canonical-trade-catalog.json"
)


def test_trade_catalog_seed_is_complete_and_idempotent() -> None:
    engine = create_engine("sqlite:///:memory:")
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    entries = load_trade_catalog(CATALOG_PATH)

    with session_factory() as session:
        first = seed_trade_catalog(session, entries)
        assert first.catalog_entries == 145
        assert first.inserted == 145
        assert first.supported == 9
        assert first.planned == 136
        assert session.scalar(select(func.count()).select_from(NicheModel)) == 145
        assert (
            session.scalar(
                select(func.count())
                .select_from(NicheModel)
                .where(NicheModel.active.is_(True))
            )
            == 9
        )

        painting = session.scalar(
            select(NicheModel).where(NicheModel.slug == "home_service_painting")
        )
        restaurant = session.scalar(
            select(NicheModel).where(NicheModel.slug == "food_restaurants")
        )
        assert painting is not None
        assert painting.catalog_status == "supported"
        assert "painter" in painting.search_config["include_terms"]
        assert restaurant is not None
        assert restaurant.catalog_status == "planned"
        assert restaurant.active is False

        second = seed_trade_catalog(session, entries)
        assert second.inserted == 0
        assert second.updated == 0
        assert second.unchanged == 145


def test_trade_catalog_does_not_promote_a_workspace_custom_trade() -> None:
    engine = create_engine("sqlite:///:memory:")
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    entries = load_trade_catalog(CATALOG_PATH)

    with session_factory() as session:
        session.add(WorkspaceModel(id="workspace:test", name="Test"))
        session.add(
            NicheModel(
                id="niche_custom_restaurants",
                slug="food_restaurants",
                label="My restaurants",
                category="custom",
                active=True,
                catalog_status="custom",
                created_by_workspace_id="workspace:test",
            )
        )
        session.commit()

        summary = seed_trade_catalog(session, entries)
        custom = session.get(NicheModel, "niche_custom_restaurants")
        assert summary.conflicts == 1
        assert custom is not None
        assert custom.label == "My restaurants"
        assert custom.catalog_status == "custom"
        assert custom.created_by_workspace_id == "workspace:test"
