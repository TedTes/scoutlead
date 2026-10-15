from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from auth.context import AuthContext
from db.models import UserModel, WorkspaceMemberModel, WorkspaceModel
from shared.utils import new_id, utcnow


class AuthRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def sync_user_workspace(self, context: AuthContext) -> AuthContext:
        if context.service_account or not context.user_id or not context.workspace_id:
            return context

        now = utcnow()
        insert = _insert_for(self.session)

        user_insert = insert(UserModel).values(
            id=context.user_id,
            clerk_user_id=context.user_id,
            email=context.email,
            last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
        self.session.execute(
            user_insert.on_conflict_do_update(
                index_elements=[UserModel.id],
                set_={
                    "email": func.coalesce(user_insert.excluded.email, UserModel.email),
                    "last_seen_at": now,
                    "updated_at": now,
                },
            )
        )

        organization_id = _organization_id(context.workspace_id, context.user_id)
        workspace_insert = insert(WorkspaceModel).values(
            id=context.workspace_id,
            name=context.email or "Personal workspace",
            clerk_organization_id=organization_id,
            created_at=now,
            updated_at=now,
        )
        if organization_id:
            workspace_statement = workspace_insert.on_conflict_do_update(
                index_elements=[WorkspaceModel.id],
                set_={
                    "clerk_organization_id": organization_id,
                    "updated_at": now,
                },
            )
        else:
            workspace_statement = workspace_insert.on_conflict_do_nothing(
                index_elements=[WorkspaceModel.id]
            )
        self.session.execute(workspace_statement)

        membership_insert = insert(WorkspaceMemberModel).values(
            id=new_id("member"),
            workspace_id=context.workspace_id,
            user_id=context.user_id,
            role="owner",
            created_at=now,
            updated_at=now,
        )
        self.session.execute(
            membership_insert.on_conflict_do_nothing(
                index_elements=[
                    WorkspaceMemberModel.workspace_id,
                    WorkspaceMemberModel.user_id,
                ]
            )
        )

        self.session.commit()
        return context


def _organization_id(workspace_id: str, user_id: str) -> str | None:
    return None if workspace_id == f"user:{user_id}" else workspace_id


def _insert_for(session: Session):
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        return postgresql_insert
    if dialect == "sqlite":
        return sqlite_insert
    raise RuntimeError(f"Unsupported database dialect for auth provisioning: {dialect}")
