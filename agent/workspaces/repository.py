from sqlalchemy.orm import Session

from db.models import WorkspaceModel
from products.repository import DEFAULT_WORKSPACE_ID
from shared.errors import NotFoundError
from shared.utils import utcnow
from workspaces.schemas import SenderProfileRead, SenderProfileUpdate


class WorkspaceRepository:
    def __init__(self, session: Session, *, workspace_id: str | None) -> None:
        self.session = session
        self.workspace_id = workspace_id or DEFAULT_WORKSPACE_ID

    def sender_profile(self) -> SenderProfileRead:
        workspace = self._get()
        return _profile_read(workspace)

    def update_sender_profile(self, update: SenderProfileUpdate) -> SenderProfileRead:
        workspace = self._get()
        for field, value in update.model_dump(exclude_unset=True).items():
            setattr(workspace, field, value)
        workspace.updated_at = utcnow()
        self.session.commit()
        self.session.refresh(workspace)
        return _profile_read(workspace)

    def _get(self) -> WorkspaceModel:
        workspace = self.session.get(WorkspaceModel, self.workspace_id)
        if workspace is None:
            raise NotFoundError("workspace not found", {"workspace_id": self.workspace_id})
        return workspace


def _profile_read(workspace: WorkspaceModel) -> SenderProfileRead:
    values = (
        workspace.sender_legal_name,
        workspace.sender_mailing_address,
        workspace.sender_contact,
    )
    return SenderProfileRead(
        workspace_id=workspace.id,
        sender_legal_name=workspace.sender_legal_name,
        sender_mailing_address=workspace.sender_mailing_address,
        sender_contact=workspace.sender_contact,
        complete=all(value and value.strip() for value in values),
    )
