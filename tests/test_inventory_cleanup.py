from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from canonical.repository import CanonicalRepository
from db.models import BusinessFactModel, BusinessModel
from db.session import create_database
from quality.inventory_cleanup import cleanup_search_origin_inventory
from source_observations.families import source_family


def _factory():
    engine = create_engine("sqlite:///:memory:")
    create_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_search_origin_cleanup_is_dry_run_first_and_preserves_structured_entities() -> None:
    factory = _factory()
    with factory() as session:
        canonical = CanonicalRepository(session)
        result_page = canonical.upsert_from_discovery_result(
            company_name="Best 15 House Painters & Painting Companies in Toronto, ON",
            geography="Toronto",
            source="configured_search",
            raw={"url": "https://example.test/best-painters"},
        )
        plausible = canonical.upsert_from_discovery_result(
            company_name="Actual Name Painting",
            geography="Toronto",
            source="configured_search",
            raw={"url": "https://actual-name.example"},
        )
        structured = canonical.upsert_from_discovery_result(
            company_name="Structured Painter",
            geography="Toronto",
            source="configured_search",
            raw={"url": "https://structured.example"},
        )
        business = session.get(BusinessModel, structured.business_id)
        canonical.record_business_evidence(
            business=business,
            source="google_places",
            raw={"id": "places/structured-painter", "name": "Structured Painter"},
        )

        dry_run = cleanup_search_origin_inventory(session)
        assert dry_run.archived == 1
        assert dry_run.quarantined == 1
        assert dry_run.retained == 1
        assert session.get(BusinessModel, result_page.business_id).status == "active"

        applied = cleanup_search_origin_inventory(session, apply=True)
        assert applied.archived == 1
        assert applied.quarantined == 1
        assert session.get(BusinessModel, result_page.business_id).status == "archived"
        assert session.get(BusinessModel, plausible.business_id).status == "quarantined"
        assert session.get(BusinessModel, structured.business_id).status == "active"
        assert list(session.scalars(select(BusinessFactModel))) == []


def test_source_families_do_not_count_inspections_as_independent_discovery() -> None:
    assert source_family("google_places") == "independent_discovery"
    assert source_family("openstreetmap") == "independent_discovery"
    assert source_family("configured_search") == "verification"
    assert source_family("company_website_signal") == "derived_inspection"
    assert source_family("pagespeed_mobile") == "derived_inspection"
