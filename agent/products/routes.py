from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.dependencies import AppServices, DbSession, get_services
from products.schemas import (
    ProductCreate,
    ProductDescriptionCreate,
    ProductIcpSuggestionRequest,
    ProductIcpSuggestionResponse,
    ProductRead,
    ProductUpdate,
)
from products.service import ProductService

router = APIRouter(prefix="/products", tags=["products"])


def _service(
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
) -> ProductService:
    return ProductService(
        session,
        llm=services.llm,
        browser=services.browser,
        search=services.search,
    )


@router.post("", response_model=ProductRead)
def create_product(
    product: ProductCreate,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return _service(session, services).create(product)


@router.post("/from-description", response_model=ProductRead)
def create_product_from_description(
    request: ProductDescriptionCreate,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return _service(session, services).create_from_description(request)


@router.post("/icp-suggestions", response_model=ProductIcpSuggestionResponse)
def suggest_product_icps(
    request: ProductIcpSuggestionRequest,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return _service(session, services).suggest_icps(request)


@router.get("", response_model=list[ProductRead])
def list_products(
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return _service(session, services).list()


@router.get("/{product_id}", response_model=ProductRead)
def get_product(
    product_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return _service(session, services).get(product_id)


@router.patch("/{product_id}", response_model=ProductRead)
def update_product(
    product_id: str,
    update: ProductUpdate,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return _service(session, services).update(product_id, update)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    _service(session, services).delete(product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
