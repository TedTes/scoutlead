from fastapi import APIRouter, Request, status

from app.dependencies import CurrentAuth, DbSession
from outreach_packages.schemas import OutreachPackageRead, OutreachPackageUpdate
from outreach_packages.service import OutreachPackageService


router = APIRouter(prefix="/outreach-packages", tags=["outreach-packages"])


def _service(request: Request, session: DbSession, workspace_id: str | None) -> OutreachPackageService:
    settings = request.app.state.services.settings
    provider = "anthropic" if settings.anthropic_api_key else "openai" if settings.openai_api_key else "remote"
    model = settings.anthropic_model if settings.anthropic_api_key else settings.openai_model if settings.openai_api_key else settings.llm_model
    return OutreachPackageService(
        session,
        llm=request.app.state.services.demo_llm,
        workspace_id=workspace_id,
        provider=provider,
        model=model,
    )


@router.get("/by-result/{result_id}", response_model=OutreachPackageRead | None)
def get_for_result(result_id: str, request: Request, session: DbSession, auth: CurrentAuth):
    return _service(request, session, auth.workspace_id).find_for_result(result_id)


@router.post(
    "/from-result/{result_id}",
    response_model=OutreachPackageRead,
    status_code=status.HTTP_201_CREATED,
)
def generate_for_result(result_id: str, request: Request, session: DbSession, auth: CurrentAuth):
    return _service(request, session, auth.workspace_id).generate(result_id)


@router.patch("/{package_id}", response_model=OutreachPackageRead)
def update_package(
    package_id: str,
    data: OutreachPackageUpdate,
    request: Request,
    session: DbSession,
    auth: CurrentAuth,
):
    return _service(request, session, auth.workspace_id).update(package_id, data)
