from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.session import create_database
from products.repository import ProductRepository
from products.schemas import ProductCreate, QualificationCriterion
from workspaces.repository import WorkspaceRepository
from workspaces.schemas import SenderProfileUpdate


def test_sender_profile_is_workspace_scoped_and_reports_completeness() -> None:
    engine = create_engine("sqlite:///:memory:")
    create_database(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        ProductRepository(session, workspace_id="workspace:first").create(
            ProductCreate(
                product_name="Coverage",
                offer_summary="Commercial insurance.",
                target_customer="HVAC contractors",
                target_geography="Toronto",
                qualification_criteria=[QualificationCriterion(label="HVAC business")],
            )
        )
        repository = WorkspaceRepository(session, workspace_id="workspace:first")
        assert repository.sender_profile().complete is False

        profile = repository.update_sender_profile(
            SenderProfileUpdate(
                sender_legal_name="  Example Brokerage Inc. ",
                sender_mailing_address=" 100 King Street, Toronto, ON ",
                sender_contact=" compliance@example.test ",
            )
        )

        assert profile.complete is True
        assert profile.sender_legal_name == "Example Brokerage Inc."
        assert profile.sender_contact == "compliance@example.test"
