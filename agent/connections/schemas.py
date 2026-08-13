from typing import Literal

from pydantic import BaseModel


class ConnectionStatus(BaseModel):
    name: str
    category: str
    status: Literal["connected", "not_configured", "degraded"]
    detail: str
