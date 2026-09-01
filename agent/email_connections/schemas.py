from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, computed_field


class EmailProvider(StrEnum):
    GMAIL = "gmail"


class EmailConnectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    product_id: str
    provider: EmailProvider
    email_address: str
    scopes: list[str]
    connected_at: datetime
    disconnected_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def connected(self) -> bool:
        return self.disconnected_at is None
