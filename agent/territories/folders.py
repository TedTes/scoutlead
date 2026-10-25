from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from db.models import AudienceFolderModel, ProductModel, TerritoryModel
from shared.errors import ConflictError, NotFoundError, ValidationError
from shared.utils import new_id, utcnow
from territories.schemas import AudienceFolderCreate, AudienceFolderRead


class AudienceFolderService:
    def __init__(self, session: Session, *, workspace_id: str) -> None:
        self.session = session
        self.workspace_id = workspace_id

    def list(self, *, product_id: str) -> list[AudienceFolderRead]:
        self._product(product_id)
        counts = dict(
            self.session.execute(
                select(TerritoryModel.folder_id, func.count(TerritoryModel.id))
                .where(
                    TerritoryModel.workspace_id == self.workspace_id,
                    TerritoryModel.product_id == product_id,
                    TerritoryModel.status != "archived",
                    TerritoryModel.folder_id.is_not(None),
                )
                .group_by(TerritoryModel.folder_id)
            ).all()
        )
        folders = list(
            self.session.scalars(
                select(AudienceFolderModel)
                .where(
                    AudienceFolderModel.workspace_id == self.workspace_id,
                    AudienceFolderModel.product_id == product_id,
                )
                .order_by(AudienceFolderModel.sort_order, AudienceFolderModel.name)
            )
        )
        return [
            AudienceFolderRead.model_validate(folder).model_copy(
                update={"audience_count": int(counts.get(folder.id, 0))}
            )
            for folder in folders
        ]

    def get(self, folder_id: str) -> AudienceFolderModel:
        folder = self.session.scalar(
            select(AudienceFolderModel).where(
                AudienceFolderModel.id == folder_id,
                AudienceFolderModel.workspace_id == self.workspace_id,
            )
        )
        if folder is None:
            raise NotFoundError("audience folder not found", {"folder_id": folder_id})
        return folder

    def create(self, data: AudienceFolderCreate) -> AudienceFolderRead:
        self._product(data.product_id)
        name = self._available_name(data.product_id, data.name)
        max_order = self.session.scalar(
            select(func.max(AudienceFolderModel.sort_order)).where(
                AudienceFolderModel.workspace_id == self.workspace_id,
                AudienceFolderModel.product_id == data.product_id,
            )
        )
        folder = AudienceFolderModel(
            id=new_id("audience_folder"),
            workspace_id=self.workspace_id,
            product_id=data.product_id,
            name=name,
            sort_order=int(max_order or 0) + 1,
        )
        self.session.add(folder)
        self.session.commit()
        self.session.refresh(folder)
        return AudienceFolderRead.model_validate(folder)

    def rename(self, folder_id: str, name: str) -> AudienceFolderRead:
        folder = self.get(folder_id)
        folder.name = self._available_name(folder.product_id, name, exclude_id=folder.id)
        folder.updated_at = utcnow()
        self.session.commit()
        self.session.refresh(folder)
        count = self.session.scalar(
            select(func.count(TerritoryModel.id)).where(
                TerritoryModel.folder_id == folder.id,
                TerritoryModel.status != "archived",
            )
        )
        return AudienceFolderRead.model_validate(folder).model_copy(
            update={"audience_count": int(count or 0)}
        )

    def delete(self, folder_id: str) -> None:
        folder = self.get(folder_id)
        self.session.execute(
            update(TerritoryModel)
            .where(TerritoryModel.folder_id == folder.id)
            .values(folder_id=None)
        )
        self.session.delete(folder)
        self.session.commit()

    def _product(self, product_id: str) -> ProductModel:
        product = self.session.scalar(
            select(ProductModel).where(
                ProductModel.id == product_id,
                ProductModel.workspace_id == self.workspace_id,
                ProductModel.archived_at.is_(None),
            )
        )
        if product is None:
            raise NotFoundError("product not found", {"product_id": product_id})
        return product

    def _available_name(
        self,
        product_id: str,
        name: str,
        *,
        exclude_id: str | None = None,
    ) -> str:
        cleaned = " ".join(name.split())
        if not cleaned:
            raise ValidationError("folder name is required")
        statement = select(AudienceFolderModel.id).where(
            AudienceFolderModel.workspace_id == self.workspace_id,
            AudienceFolderModel.product_id == product_id,
            func.lower(AudienceFolderModel.name) == cleaned.lower(),
        )
        if exclude_id:
            statement = statement.where(AudienceFolderModel.id != exclude_id)
        if self.session.scalar(statement) is not None:
            raise ConflictError("audience folder already exists", {"name": cleaned})
        return cleaned
