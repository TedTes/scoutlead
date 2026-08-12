from sqlalchemy.orm import Session

from db.models import ProductModel
from products.repository import ProductRepository
from products.schemas import ProductCreate, ProductUpdate


class ProductService:
    def __init__(self, session: Session) -> None:
        self.products = ProductRepository(session)

    def create(self, product: ProductCreate) -> ProductModel:
        return self.products.create(product)

    def list(self) -> list[ProductModel]:
        return self.products.list()

    def get(self, product_id: str) -> ProductModel:
        return self.products.get(product_id)

    def update(self, product_id: str, update: ProductUpdate) -> ProductModel:
        return self.products.update(product_id, update)
