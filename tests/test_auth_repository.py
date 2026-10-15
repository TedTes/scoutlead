from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from auth.context import AuthContext
from auth.repository import AuthRepository
from db.base import Base
from db.models import UserModel, WorkspaceMemberModel, WorkspaceModel


def _session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_sync_user_workspace_is_idempotent_and_updates_user() -> None:
    session_factory = _session_factory()
    context = AuthContext(
        user_id="user_123",
        workspace_id="user:user_123",
        email="first@example.com",
    )

    with session_factory() as session:
        repository = AuthRepository(session)
        repository.sync_user_workspace(context)
        repository.sync_user_workspace(
            AuthContext(
                user_id="user_123",
                workspace_id="user:user_123",
                email="updated@example.com",
            )
        )

        user = session.get(UserModel, "user_123")
        assert user is not None
        assert user.email == "updated@example.com"
        assert session.scalar(select(func.count()).select_from(UserModel)) == 1
        assert session.scalar(select(func.count()).select_from(WorkspaceModel)) == 1
        assert session.scalar(select(func.count()).select_from(WorkspaceMemberModel)) == 1


def test_sync_user_workspace_creates_organization_membership() -> None:
    session_factory = _session_factory()
    context = AuthContext(
        user_id="user_123",
        workspace_id="org_456",
        email="owner@example.com",
    )

    with session_factory() as session:
        AuthRepository(session).sync_user_workspace(context)

        workspace = session.get(WorkspaceModel, "org_456")
        membership = session.scalar(select(WorkspaceMemberModel))
        assert workspace is not None
        assert workspace.clerk_organization_id == "org_456"
        assert membership is not None
        assert membership.workspace_id == "org_456"
        assert membership.user_id == "user_123"
