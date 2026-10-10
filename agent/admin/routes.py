from fastapi import APIRouter, Query, Response

from admin.schemas import (
    AdminActionReason,
    AdminBusinessCreate,
    AdminBusinessStateChange,
    AdminBusinessUpdate,
    AdminDeleteRequest,
)
from admin.service import AdminDataService
from app.dependencies import AdminAuth, DbSession


router = APIRouter(prefix="/admin", tags=["admin"])


def _service(session: DbSession, auth: AdminAuth) -> AdminDataService:
    return AdminDataService(session, auth)


@router.get("/access")
def admin_access(auth: AdminAuth):
    return {"is_admin": True, "email": auth.email}


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
