from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import EmailConnectionModel
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

    def upsert(
        self,
        *,
        product_id: str,
        provider: EmailProvider | str,
        email_address: str,
        encrypted_refresh_token: str,
        scopes: list[str],
    ) -> EmailConnectionModel:
        provider_value = provider.value if isinstance(provider, EmailProvider) else provider
        model = self.get_for_product(product_id, provider_value)
        now = utcnow()
        if model is None:
            model = EmailConnectionModel(
                id=new_id("email_connection"),
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
        product_id: str,
        provider: EmailProvider | str = EmailProvider.GMAIL,
    ) -> EmailConnectionModel:
        provider_value = provider.value if isinstance(provider, EmailProvider) else provider
        model = self.get_for_product(product_id, provider_value)
        if model is None:
            raise NotFoundError(
                "email connection not found",
                {"product_id": product_id, "provider": provider_value},
            )
        model.disconnected_at = utcnow()
        model.encrypted_refresh_token = None
        self.session.commit()
        self.session.refresh(model)
        return model

    def set_last_error(self, connection_id: str, error: str | None) -> EmailConnectionModel:
        model = self.get(connection_id)
        model.last_error = error
        model.updated_at = utcnow()
        self.session.commit()
        self.session.refresh(model)
        return model
