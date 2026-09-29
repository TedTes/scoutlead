from fastapi import APIRouter

from app.dependencies import CurrentAuth, DbSession
from workspaces.repository import WorkspaceRepository
from workspaces.schemas import SenderProfileRead, SenderProfileUpdate


router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("/sender-profile", response_model=SenderProfileRead)
def get_sender_profile(session: DbSession, auth: CurrentAuth):
    return WorkspaceRepository(session, workspace_id=auth.workspace_id).sender_profile()


@router.patch("/sender-profile", response_model=SenderProfileRead)
def update_sender_profile(
    update: SenderProfileUpdate,
    session: DbSession,
    auth: CurrentAuth,
):
    return WorkspaceRepository(session, workspace_id=auth.workspace_id).update_sender_profile(
        update
    )
