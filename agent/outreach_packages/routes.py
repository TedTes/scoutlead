from fastapi import APIRouter, status

from app.dependencies import CurrentAuth, DbSession
from outreach_packages.schemas import OutreachPackageRead, OutreachPackageUpdate
from outreach_packages.service import OutreachPackageService


router = APIRouter(prefix="/outreach-packages", tags=["outreach-packages"])


def _service(session: DbSession, workspace_id: str | None) -> OutreachPackageService:
    return OutreachPackageService(
        session,
        workspace_id=workspace_id,
    )


@router.get("/by-result/{result_id}", response_model=OutreachPackageRead | None)
def get_for_result(result_id: str, session: DbSession, auth: CurrentAuth):
    return _service(session, auth.workspace_id).find_for_result(result_id)


@router.post(
    "/from-result/{result_id}",
    response_model=OutreachPackageRead,
    status_code=status.HTTP_201_CREATED,
)
def generate_for_result(result_id: str, session: DbSession, auth: CurrentAuth):
    return _service(session, auth.workspace_id).generate(result_id)


@router.patch("/{package_id}", response_model=OutreachPackageRead)
def update_package(
    package_id: str,
    data: OutreachPackageUpdate,
    session: DbSession,
    auth: CurrentAuth,
):
    return _service(session, auth.workspace_id).update(package_id, data)
