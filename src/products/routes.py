from fastapi import APIRouter

from app.dependencies import DbSession
from products.schemas import ProductCreate, ProductRead, ProductUpdate
from products.service import ProductService

router = APIRouter(prefix="/products", tags=["products"])


@router.post("", response_model=ProductRead)
def create_product(product: ProductCreate, session: DbSession):
    return ProductService(session).create(product)


@router.get("", response_model=list[ProductRead])
def list_products(session: DbSession):
    return ProductService(session).list()


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: str, session: DbSession):
    return ProductService(session).get(product_id)


@router.patch("/{product_id}", response_model=ProductRead)
def update_product(product_id: str, update: ProductUpdate, session: DbSession):
    return ProductService(session).update(product_id, update)
