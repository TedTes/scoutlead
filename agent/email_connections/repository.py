from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import EmailConnectionModel, ProductModel
from email_connections.schemas import EmailProvider
from shared.errors import NotFoundError
from shared.utils import new_id, utcnow


class EmailConnectionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, connection_id: str) -> EmailConnectionModel:
        model = self.session.get(EmailConnectionModel, connection_id)
        if model is None:
            raise NotFoundError("email connection not found", {"connection_id": connection_id})
        return model

    def get_for_product(
        self,
        product_id: str,
        provider: EmailProvider | str = EmailProvider.GMAIL,
    ) -> EmailConnectionModel | None:
        provider_value = provider.value if isinstance(provider, EmailProvider) else provider
        return self.session.scalar(
            select(EmailConnectionModel)
            .where(EmailConnectionModel.product_id == product_id)
            .where(EmailConnectionModel.provider == provider_value)
            .limit(1)
        )

    def get_for_workspace(
        self,
        workspace_id: str,
        provider: EmailProvider | str = EmailProvider.GMAIL,
    ) -> EmailConnectionModel | None:
        provider_value = provider.value if isinstance(provider, EmailProvider) else provider
        return self.session.scalar(
            select(EmailConnectionModel)
            .where(EmailConnectionModel.workspace_id == workspace_id)
            .where(EmailConnectionModel.provider == provider_value)
            .limit(1)
        )

    def get_active_for_product(
        self,
        product_id: str,
        provider: EmailProvider | str = EmailProvider.GMAIL,
    ) -> EmailConnectionModel | None:
        provider_value = provider.value if isinstance(provider, EmailProvider) else provider
        return self.session.scalar(
            select(EmailConnectionModel)
            .where(EmailConnectionModel.product_id == product_id)
            .where(EmailConnectionModel.provider == provider_value)
            .where(EmailConnectionModel.disconnected_at.is_(None))
            .limit(1)
        )

    def get_active_for_workspace(
        self,
        workspace_id: str,
        provider: EmailProvider | str = EmailProvider.GMAIL,
    ) -> EmailConnectionModel | None:
        provider_value = provider.value if isinstance(provider, EmailProvider) else provider
        return self.session.scalar(
            select(EmailConnectionModel)
            .where(EmailConnectionModel.workspace_id == workspace_id)
            .where(EmailConnectionModel.provider == provider_value)
            .where(EmailConnectionModel.disconnected_at.is_(None))
            .limit(1)
        )

    def upsert(
        self,
        *,
        workspace_id: str | None = None,
        product_id: str | None = None,
        provider: EmailProvider | str,
        email_address: str,
        encrypted_refresh_token: str,
        scopes: list[str],
    ) -> EmailConnectionModel:
        provider_value = provider.value if isinstance(provider, EmailProvider) else provider
        resolved_workspace_id = workspace_id or self._workspace_id_for_product(product_id)
        model = self.get_for_workspace(resolved_workspace_id, provider_value)
        now = utcnow()
        if model is None:
            model = EmailConnectionModel(
                id=new_id("email_connection"),
                workspace_id=resolved_workspace_id,
                product_id=product_id,
                provider=provider_value,
                email_address=email_address,
                encrypted_refresh_token=encrypted_refresh_token,
                scopes=scopes,
                connected_at=now,
                disconnected_at=None,
                last_error=None,
            )
            self.session.add(model)
        else:
            model.workspace_id = resolved_workspace_id
            model.product_id = product_id
            model.email_address = email_address
            model.encrypted_refresh_token = encrypted_refresh_token
            model.scopes = scopes
            model.connected_at = now
            model.disconnected_at = None
            model.last_error = None
            model.updated_at = now
        self.session.commit()
        self.session.refresh(model)
        return model

    def disconnect(
        self,
        workspace_id: str | None = None,
        product_id: str | None = None,
        provider: EmailProvider | str = EmailProvider.GMAIL,
    ) -> EmailConnectionModel:
        provider_value = provider.value if isinstance(provider, EmailProvider) else provider
        if workspace_id:
            model = self.get_for_workspace(workspace_id, provider_value)
        else:
            model = self.get_for_product(product_id or "", provider_value) if product_id else None
        if model is None:
            raise NotFoundError(
                "email connection not found",
                {"workspace_id": workspace_id, "product_id": product_id, "provider": provider_value},
            )
        model.disconnected_at = utcnow()
        model.encrypted_refresh_token = None
        self.session.commit()
        self.session.refresh(model)
        return model

    def _workspace_id_for_product(self, product_id: str | None) -> str:
        if not product_id:
            raise NotFoundError("email connection workspace not found", {"product_id": product_id})
        workspace_id = self.session.scalar(
            select(ProductModel.workspace_id).where(ProductModel.id == product_id).limit(1)
        )
        if not workspace_id:
            raise NotFoundError("email connection workspace not found", {"product_id": product_id})
        return workspace_id

    def set_last_error(self, connection_id: str, error: str | None) -> EmailConnectionModel:
        model = self.get(connection_id)
        model.last_error = error
        model.updated_at = utcnow()
        self.session.commit()
        self.session.refresh(model)
        return model
