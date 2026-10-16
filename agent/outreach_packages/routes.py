from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.dependencies import AppServices, CurrentAuth, DbSession, get_services
from outreach_packages.schemas import (
    DraftAlternative,
    OutreachAISuggestionRequest,
    OutreachAnalyticsRead,
    OutreachEventCreate,
    OutreachEventRead,
    OutreachPackageRead,
    OutreachPackageUpdate,
    OutreachResponseClassification,
    OutreachResponseClassifyRequest,
)
from outreach_packages.service import OutreachPackageService


router = APIRouter(prefix="/outreach-packages", tags=["outreach-packages"])


Services = Annotated[AppServices, Depends(get_services)]


def _service(
    session: DbSession,
    workspace_id: str | None,
    services: AppServices,
) -> OutreachPackageService:
    return OutreachPackageService(
        session,
        workspace_id=workspace_id,
        llm=services.llm,
        ai_mode=services.settings.outreach_ai_mode,
    )


@router.get("/by-result/{result_id}", response_model=OutreachPackageRead | None)
def get_for_result(result_id: str, session: DbSession, auth: CurrentAuth, services: Services):
    return _service(session, auth.workspace_id, services).find_for_result(result_id)


@router.post(
    "/from-result/{result_id}",
    response_model=OutreachPackageRead,
    status_code=status.HTTP_201_CREATED,
)
def generate_for_result(result_id: str, session: DbSession, auth: CurrentAuth, services: Services):
    return _service(session, auth.workspace_id, services).generate(result_id)


@router.patch("/{package_id}", response_model=OutreachPackageRead)
def update_package(
    package_id: str,
    data: OutreachPackageUpdate,
    session: DbSession,
    auth: CurrentAuth,
    services: Services,
):
    return _service(session, auth.workspace_id, services).update(package_id, data)


@router.post("/{package_id}/ai-suggestion", response_model=DraftAlternative)
def generate_ai_suggestion(
    package_id: str,
    data: OutreachAISuggestionRequest,
    session: DbSession,
    auth: CurrentAuth,
    services: Services,
):
    return _service(session, auth.workspace_id, services).generate_ai_suggestion(package_id, data)


@router.post(
    "/{package_id}/classify-response",
    response_model=OutreachResponseClassification,
)
def classify_response(
    package_id: str,
    data: OutreachResponseClassifyRequest,
    session: DbSession,
    auth: CurrentAuth,
    services: Services,
):
    return _service(session, auth.workspace_id, services).classify_response(package_id, data)


@router.post(
    "/{package_id}/events",
    response_model=OutreachEventRead,
    status_code=status.HTTP_201_CREATED,
)
def record_event(
    package_id: str,
    data: OutreachEventCreate,
    session: DbSession,
    auth: CurrentAuth,
    services: Services,
):
    return _service(session, auth.workspace_id, services).record_event(package_id, data)


@router.get("/analytics/summary", response_model=OutreachAnalyticsRead)
def analytics(session: DbSession, auth: CurrentAuth, services: Services):
    return _service(session, auth.workspace_id, services).analytics()
