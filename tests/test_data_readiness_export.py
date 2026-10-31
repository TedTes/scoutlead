from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker

from data_readiness.export import (
    MarketScope,
    ProviderBudget,
    export_city_category,
)
from db.models import BusinessModel, ValidationResultModel
from db.session import create_database
from seeding.service import BusinessSeedService
from tests.test_business_seeding import FakeEmbeddingClient, painting_seed


def test_city_category_export_separates_quality_states_without_writes() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        BusinessSeedService(session, embedding=FakeEmbeddingClient()).import_seeds(
            [
                painting_seed(
                    company_name="Validated Painter",
                    website_url="https://validated-painter.test",
                    phone="416-555-0101",
                    contact_email="owner@validated-painter.test",
                    latitude=43.6532,
                    longitude=-79.3832,
                ),
                painting_seed(
                    company_name="Uncertain Painter",
                    website_url="https://uncertain-painter.test",
                    phone="416-555-0102",
                    contact_email="owner@uncertain-painter.test",
                    latitude=43.66,
                    longitude=-79.39,
                ),
                painting_seed(
                    company_name="Rejected Painter",
                    website_url="https://rejected-painter.test",
                    phone="416-555-0103",
                    contact_email="owner@rejected-painter.test",
                    latitude=43.67,
                    longitude=-79.40,
                ),
                painting_seed(
                    company_name="Distant Painter",
                    website_url="https://distant-painter.test",
                    phone="604-555-0104",
                    contact_email="owner@distant-painter.test",
                    latitude=49.2827,
                    longitude=-123.1207,
                ),
            ],
            batch_id="readiness-export-test",
        )
        businesses = {
            row.display_name: row for row in session.scalars(select(BusinessModel))
        }
        session.execute(
            delete(ValidationResultModel).where(
                ValidationResultModel.business_id
                == businesses["Uncertain Painter"].id,
                ValidationResultModel.validation_type == "location",
            )
        )
        rejected_trade = session.scalar(
            select(ValidationResultModel).where(
                ValidationResultModel.business_id
                == businesses["Rejected Painter"].id,
                ValidationResultModel.validation_type == "trade",
            )
        )
        assert rejected_trade is not None
        rejected_trade.status = "failed"
        rejected_trade.reason = "The provider category conflicts with painting."
        session.commit()

        before = session.query(BusinessModel).count()
        bundle = export_city_category(
            session,
            market=MarketScope("Toronto", 43.6532, -79.3832, 25),
            niche_slug="home_service_painting",
            target_count=100,
            candidate_limit=400,
            provider_budgets=(
                ProviderBudget("google_places", 10),
                ProviderBudget("openstreetmap", 1),
            ),
        )
        after = session.query(BusinessModel).count()

    assert before == after == 4
    assert [row["name"] for row in bundle["validated"]] == ["Validated Painter"]
    assert [row["name"] for row in bundle["uncertain"]] == ["Uncertain Painter"]
    assert [row["name"] for row in bundle["rejected"]] == ["Rejected Painter"]
    assert bundle["manifest"]["counts"] == {
        "memberships_considered": 4,
        "within_radius": 3,
        "within_radius_before_limit": 3,
        "candidate_limit_reached": False,
        "validated": 1,
        "uncertain": 1,
        "rejected": 1,
        "coverage_deficit": 99,
        "excluded_missing_coordinates": 0,
        "excluded_outside_radius": 1,
    }
    assert bundle["manifest"]["collection_plan"]["hard_request_cap"] == 11
    assert bundle["manifest"]["external_requests_executed"] == 0
    assert bundle["manifest"]["database_mutated"] is False


def _session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
