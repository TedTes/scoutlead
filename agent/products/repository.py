from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import ProductModel
from products.schemas import ProductCreate, ProductUpdate
from shared.errors import NotFoundError
from shared.utils import new_id, utcnow


class ProductRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, product: ProductCreate) -> ProductModel:
        data = product.model_dump(mode="json")
        self._ensure_criterion_ids(data)
        model = ProductModel(id=new_id("product"), **data)
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return model

    def list(self) -> list[ProductModel]:
        return list(self.session.scalars(select(ProductModel).order_by(ProductModel.created_at.desc())))

    def get(self, product_id: str) -> ProductModel:
        model = self.session.get(ProductModel, product_id)
        if model is None:
            raise NotFoundError("product not found", {"product_id": product_id})
        return model

    def update(self, product_id: str, update: ProductUpdate) -> ProductModel:
        model = self.get(product_id)
        data = update.model_dump(mode="json", exclude_unset=True)
        if "qualification_criteria" in data:
            self._ensure_criterion_ids(data)
        for field, value in data.items():
            setattr(model, field, value)
        model.updated_at = utcnow()
        self.session.commit()
        self.session.refresh(model)
        return model

    def archive(self, product_id: str) -> ProductModel:
        model = self.get(product_id)
        model.archived_at = utcnow()
        self.session.commit()
        self.session.refresh(model)
        return model

    @staticmethod
    def _ensure_criterion_ids(data: dict) -> None:
        for criterion in data.get("qualification_criteria", []):
            if not criterion.get("id"):
                criterion["id"] = new_id("criterion")
