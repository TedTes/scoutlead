from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.dependencies import AppServices, DbSession, get_services
from products.schemas import (
    ProductCreate,
    ProductInferenceRead,
    ProductRead,
    ProductSourceCreate,
    ProductUpdate,
)
from products.service import ProductService

router = APIRouter(prefix="/products", tags=["products"])


@router.post("", response_model=ProductRead)
def create_product(product: ProductCreate, session: DbSession):
    return ProductService(session).create(product)


@router.post("/from-source", response_model=ProductRead)
def create_product_from_source(
    request: ProductSourceCreate,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return ProductService(
        session,
        llm=services.llm,
        browser=services.browser,
        search=services.search,
    ).create_from_source(request)


@router.post("/infer-source", response_model=ProductInferenceRead)
def infer_product_from_source(
    request: ProductSourceCreate,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return ProductService(
        session,
        llm=services.llm,
        browser=services.browser,
        search=services.search,
    ).infer_product_from_source(request)


@router.get("", response_model=list[ProductRead])
def list_products(session: DbSession):
    return ProductService(session).list()


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: str, session: DbSession):
    return ProductService(session).get(product_id)


@router.patch("/{product_id}", response_model=ProductRead)
def update_product(product_id: str, update: ProductUpdate, session: DbSession):
    return ProductService(session).update(product_id, update)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: str, session: DbSession):
    ProductService(session).delete(product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
