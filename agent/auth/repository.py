from __future__ import annotations

from sqlalchemy import select
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
        user = self.session.scalar(
            select(UserModel).where(UserModel.clerk_user_id == context.user_id)
        )
        if user is None:
            user = UserModel(
                id=context.user_id,
                clerk_user_id=context.user_id,
                email=context.email,
                last_seen_at=now,
            )
            self.session.add(user)
        else:
            user.email = context.email or user.email
            user.last_seen_at = now

        workspace = self.session.get(WorkspaceModel, context.workspace_id)
        if workspace is None:
            workspace = WorkspaceModel(
                id=context.workspace_id,
                name=context.email or "Personal workspace",
                clerk_organization_id=_organization_id(context.workspace_id, context.user_id),
            )
            self.session.add(workspace)
        elif context.workspace_id != f"user:{context.user_id}":
            workspace.clerk_organization_id = context.workspace_id

        membership = self.session.scalar(
            select(WorkspaceMemberModel)
            .where(WorkspaceMemberModel.workspace_id == context.workspace_id)
            .where(WorkspaceMemberModel.user_id == user.id)
        )
        if membership is None:
            self.session.add(
                WorkspaceMemberModel(
                    id=new_id("member"),
                    workspace_id=context.workspace_id,
                    user_id=user.id,
                    role="owner",
                )
            )

        self.session.commit()
        return context


def _organization_id(workspace_id: str, user_id: str) -> str | None:
    return None if workspace_id == f"user:{user_id}" else workspace_id
