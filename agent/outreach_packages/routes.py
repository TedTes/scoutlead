from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.dependencies import AppServices, CurrentAuth, DbSession, get_services
from outreach_packages.schemas import (
    OutreachAnalyticsRead,
    OutreachEventCreate,
    OutreachEventRead,
    OutreachGenerateRequest,
    OutreachMarkSentRequest,
    OutreachPackageRead,
    OutreachPackageUpdate,
    OutreachResponseClassification,
    OutreachResponseClassifyRequest,
    OutreachTemplateCreate,
    OutreachTemplateRead,
    OutreachTemplateUpdate,
)
from outreach_packages.service import OutreachPackageService, OutreachTemplateService
from messages.schemas import MessageRead


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
    )


def _template_service(
    session: DbSession,
    workspace_id: str | None,
) -> OutreachTemplateService:
    return OutreachTemplateService(session, workspace_id=workspace_id)


@router.get("/templates", response_model=list[OutreachTemplateRead])
def list_templates(session: DbSession, auth: CurrentAuth):
    return _template_service(session, auth.workspace_id).list()


@router.post(
    "/templates",
    response_model=OutreachTemplateRead,
    status_code=status.HTTP_201_CREATED,
)
def create_template(
    data: OutreachTemplateCreate,
    session: DbSession,
    auth: CurrentAuth,
):
    return _template_service(session, auth.workspace_id).create(data)


@router.patch("/templates/{template_id}", response_model=OutreachTemplateRead)
def update_template(
    template_id: str,
    data: OutreachTemplateUpdate,
    session: DbSession,
    auth: CurrentAuth,
):
    return _template_service(session, auth.workspace_id).update(template_id, data)


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(template_id: str, session: DbSession, auth: CurrentAuth):
    _template_service(session, auth.workspace_id).delete(template_id)


@router.get("/by-result/{result_id}", response_model=OutreachPackageRead | None)
def get_for_result(
    result_id: str, session: DbSession, auth: CurrentAuth, services: Services
):
    return _service(session, auth.workspace_id, services).find_for_result(result_id)


@router.post(
    "/from-result/{result_id}",
    response_model=OutreachPackageRead,
    status_code=status.HTTP_201_CREATED,
)
def generate_for_result(
    result_id: str,
    session: DbSession,
    auth: CurrentAuth,
    services: Services,
    data: OutreachGenerateRequest | None = None,
):
    return _service(session, auth.workspace_id, services).generate(
        result_id,
        data or OutreachGenerateRequest(),
    )


@router.put(
    "/from-result/{result_id}/context",
    response_model=OutreachPackageRead,
)
def save_context_for_result(
    result_id: str,
    data: OutreachGenerateRequest,
    session: DbSession,
    auth: CurrentAuth,
    services: Services,
):
    return _service(session, auth.workspace_id, services).save_context(result_id, data)


@router.patch("/{package_id}", response_model=OutreachPackageRead)
def update_package(
    package_id: str,
    data: OutreachPackageUpdate,
    session: DbSession,
    auth: CurrentAuth,
    services: Services,
):
    return _service(session, auth.workspace_id, services).update(package_id, data)


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
    return _service(session, auth.workspace_id, services).classify_response(
        package_id, data
    )


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


@router.post("/{package_id}/mark-sent", response_model=OutreachPackageRead)
def mark_sent(
    package_id: str,
    data: OutreachMarkSentRequest,
    session: DbSession,
    auth: CurrentAuth,
    services: Services,
):
    return _service(session, auth.workspace_id, services).mark_sent(package_id, data)


@router.post("/{package_id}/message", response_model=MessageRead)
def prepare_message(
    package_id: str,
    session: DbSession,
    auth: CurrentAuth,
    services: Services,
):
    return _service(session, auth.workspace_id, services).prepare_message(package_id)


@router.get("/analytics/summary", response_model=OutreachAnalyticsRead)
def analytics(session: DbSession, auth: CurrentAuth, services: Services):
    return _service(session, auth.workspace_id, services).analytics()
