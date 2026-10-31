from fastapi import APIRouter, Query, Response

from admin.schemas import (
    AdminActionReason,
    AdminBusinessCreate,
    AdminBusinessStateChange,
    AdminBusinessUpdate,
    AdminDeleteRequest,
    AdminDataJobAction,
    AdminDataJobCreate,
    AdminSignalDefinitionCreate,
    AdminSignalCollectionRequest,
    AdminSignalDefinitionStateChange,
    AdminSignalDefinitionUpdate,
    AdminSignalValidationRequest,
    AdminServiceDefinitionCreate,
    AdminServiceDefinitionStateChange,
    AdminServiceDefinitionUpdate,
)
from admin.service import AdminDataService
from app.dependencies import AdminAuth, DbSession
from outreach_packages.schemas import (
    PlaybookAdminRead,
    PlaybookAdminStateChange,
    PlaybookAdminUpdate,
)


router = APIRouter(prefix="/admin", tags=["admin"])


def _service(session: DbSession, auth: AdminAuth) -> AdminDataService:
    return AdminDataService(session, auth)


@router.get("/access")
def admin_access(auth: AdminAuth):
    return {"is_admin": True, "email": auth.email}


@router.get("/data-jobs/segments")
def data_job_segments(session: DbSession, auth: AdminAuth):
    return _service(session, auth).list_data_segments()


@router.get("/data-jobs")
def list_data_jobs(
    session: DbSession,
    auth: AdminAuth,
    limit: int = Query(default=50, ge=1, le=200),
):
    return _service(session, auth).list_data_jobs(limit=limit)


@router.post("/data-jobs")
def create_data_job(data: AdminDataJobCreate, session: DbSession, auth: AdminAuth):
    return _service(session, auth).create_data_job(data)


@router.get("/data-jobs/{job_id}")
def data_job_detail(job_id: str, session: DbSession, auth: AdminAuth):
    return _service(session, auth).data_job_detail(job_id)


@router.post("/data-jobs/{job_id}/validate")
def validate_data_job(
    job_id: str,
    data: AdminDataJobAction,
    session: DbSession,
    auth: AdminAuth,
):
    return _service(session, auth).validate_data_job(
        job_id,
        reason=data.reason,
        sample_size=data.sample_size,
        source_item_ids=data.source_item_ids,
    )


@router.post("/data-jobs/{job_id}/discard")
def discard_data_job(
    job_id: str,
    data: AdminDataJobAction,
    session: DbSession,
    auth: AdminAuth,
):
    return _service(session, auth).discard_data_job(job_id, reason=data.reason)


@router.post("/data-jobs/{job_id}/cancel")
def cancel_data_job(
    job_id: str,
    data: AdminDataJobAction,
    session: DbSession,
    auth: AdminAuth,
):
    return _service(session, auth).cancel_data_job(job_id, reason=data.reason)


@router.post("/data-jobs/{job_id}/retry")
def retry_data_job(
    job_id: str,
    data: AdminDataJobAction,
    session: DbSession,
    auth: AdminAuth,
):
    return _service(session, auth).retry_data_job(job_id, reason=data.reason)


@router.get("/signals")
def list_signal_definitions(
    session: DbSession,
    auth: AdminAuth,
    status: str | None = None,
):
    return _service(session, auth).list_signal_definitions(status=status)


@router.post("/signals")
def create_signal_definition(
    data: AdminSignalDefinitionCreate,
    session: DbSession,
    auth: AdminAuth,
):
    return _service(session, auth).create_signal_definition(data)


@router.post("/signals/collect-active")
def collect_active_signal_definitions(
    data: AdminSignalCollectionRequest,
    session: DbSession,
    auth: AdminAuth,
):
    return _service(session, auth).collect_active_signal_definitions(
        reason=data.reason,
        scope=data.scope,
        business_ids=data.business_ids,
        niche_slug=data.niche_slug,
        market_key=data.market_key,
        batch_size=data.batch_size,
    )


@router.patch("/signals/{signal_id}")
def update_signal_definition(
    signal_id: str,
    data: AdminSignalDefinitionUpdate,
    session: DbSession,
    auth: AdminAuth,
):
    return _service(session, auth).update_signal_definition(signal_id, data)


@router.post("/signals/{signal_id}/status")
def change_signal_definition_status(
    signal_id: str,
    data: AdminSignalDefinitionStateChange,
    session: DbSession,
    auth: AdminAuth,
):
    return _service(session, auth).change_signal_definition_status(
        signal_id,
        status=data.status,
        reason=data.reason,
        scope=data.scope,
        business_ids=data.business_ids,
        niche_slug=data.niche_slug,
        market_key=data.market_key,
        batch_size=data.batch_size,
    )


@router.post("/signals/{signal_id}/collect")
def collect_signal_definition(
    signal_id: str,
    data: AdminSignalCollectionRequest,
    session: DbSession,
    auth: AdminAuth,
):
    return _service(session, auth).collect_signal_definition(
        signal_id,
        reason=data.reason,
        scope=data.scope,
        business_ids=data.business_ids,
        niche_slug=data.niche_slug,
        market_key=data.market_key,
        batch_size=data.batch_size,
    )


@router.post("/signals/{signal_id}/validate")
def validate_signal_facts(
    signal_id: str,
    data: AdminSignalValidationRequest,
    session: DbSession,
    auth: AdminAuth,
):
    return _service(session, auth).validate_signal_facts(
        signal_id,
        decision=data.decision,
        reason=data.reason,
        scope=data.scope,
        business_ids=data.business_ids,
    )


@router.get("/services")
def list_service_definitions(
    session: DbSession,
    auth: AdminAuth,
    status: str | None = None,
):
    return _service(session, auth).list_service_definitions(status=status)


@router.post("/services")
def create_service_definition(
    data: AdminServiceDefinitionCreate,
    session: DbSession,
    auth: AdminAuth,
):
    return _service(session, auth).create_service_definition(data)


@router.patch("/services/{service_id}")
def update_service_definition(
    service_id: str,
    data: AdminServiceDefinitionUpdate,
    session: DbSession,
    auth: AdminAuth,
):
    return _service(session, auth).update_service_definition(service_id, data)


@router.post("/services/{service_id}/status")
def change_service_definition_status(
    service_id: str,
    data: AdminServiceDefinitionStateChange,
    session: DbSession,
    auth: AdminAuth,
):
    return _service(session, auth).change_service_definition_status(
        service_id,
        status=data.status,
        reason=data.reason,
    )


@router.post("/services/{service_id}/collect")
def collect_service_signals(
    service_id: str,
    data: AdminSignalCollectionRequest,
    session: DbSession,
    auth: AdminAuth,
):
    return _service(session, auth).collect_service_signals(
        service_id,
        reason=data.reason,
        scope=data.scope,
        business_ids=data.business_ids,
        niche_slug=data.niche_slug,
        market_key=data.market_key,
        batch_size=data.batch_size,
    )


@router.get("/outreach-playbooks", response_model=list[PlaybookAdminRead])
def list_outreach_playbooks(session: DbSession, auth: AdminAuth):
    return _service(session, auth).list_outreach_playbooks()


@router.put("/outreach-playbooks/{service_key}", response_model=PlaybookAdminRead)
def update_outreach_playbook(
    service_key: str,
    data: PlaybookAdminUpdate,
    session: DbSession,
    auth: AdminAuth,
):
    return _service(session, auth).update_outreach_playbook(
        service_key,
        definition=data.definition,
        reason=data.reason,
    )


@router.post("/outreach-playbooks/{service_key}/status", response_model=PlaybookAdminRead)
def change_outreach_playbook_status(
    service_key: str,
    data: PlaybookAdminStateChange,
    session: DbSession,
    auth: AdminAuth,
):
    return _service(session, auth).change_outreach_playbook_status(
        service_key,
        status=data.status,
        reason=data.reason,
    )


@router.get("/businesses/overview")
def business_overview(session: DbSession, auth: AdminAuth):
    return _service(session, auth).overview()


@router.get("/businesses")
def list_businesses(
    session: DbSession,
    auth: AdminAuth,
    q: str | None = None,
    validation: str | None = None,
    status: str | None = None,
    niche_slug: str | None = None,
    market_key: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=10, le=200),
):
    return _service(session, auth).list_businesses(
        query=q,
        validation=validation,
        status=status,
        niche_slug=niche_slug,
        market_key=market_key,
        page=page,
        page_size=page_size,
    )


@router.post("/businesses")
def create_business(data: AdminBusinessCreate, session: DbSession, auth: AdminAuth):
    return _service(session, auth).create(data)


@router.get("/businesses/{business_id}")
def business_detail(business_id: str, session: DbSession, auth: AdminAuth):
    return _service(session, auth).detail(business_id)


@router.get("/businesses/{business_id}/fact-lineage")
def business_fact_lineage(business_id: str, session: DbSession, auth: AdminAuth):
    return _service(session, auth).fact_lineage(business_id)


@router.patch("/businesses/{business_id}")
def update_business(
    business_id: str,
    data: AdminBusinessUpdate,
    session: DbSession,
    auth: AdminAuth,
):
    return _service(session, auth).update(business_id, data)


@router.post("/businesses/{business_id}/status")
def change_business_status(
    business_id: str,
    data: AdminBusinessStateChange,
    session: DbSession,
    auth: AdminAuth,
):
    return _service(session, auth).change_status(business_id, data.status, data.reason)


@router.post("/businesses/{business_id}/revalidate")
def revalidate_business(
    business_id: str,
    data: AdminActionReason,
    session: DbSession,
    auth: AdminAuth,
):
    return _service(session, auth).revalidate(business_id, data.reason)


@router.get("/businesses/{business_id}/delete-dependencies")
def business_delete_dependencies(
    business_id: str,
    session: DbSession,
    auth: AdminAuth,
):
    return _service(session, auth).delete_dependencies(business_id)


@router.delete("/businesses/{business_id}", status_code=204)
def delete_business(
    business_id: str,
    data: AdminDeleteRequest,
    session: DbSession,
    auth: AdminAuth,
):
    _service(session, auth).delete(business_id, data.confirmation, data.reason)
    return Response(status_code=204)
