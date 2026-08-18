from fastapi import APIRouter, Response, status

from app.dependencies import DbSession
from products.schemas import (
    ProductCreate,
    ProductDescriptionCreate,
    ProductRead,
    ProductUpdate,
)
from products.service import ProductService

router = APIRouter(prefix="/products", tags=["products"])


@router.post("", response_model=ProductRead)
def create_product(product: ProductCreate, session: DbSession):
    return ProductService(session).create(product)


@router.post("/from-description", response_model=ProductRead)
def create_product_from_description(request: ProductDescriptionCreate, session: DbSession):
    return ProductService(session).create_from_description(request)


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
