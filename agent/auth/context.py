from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthContext:
    user_id: str | None = None
    workspace_id: str | None = None
    email: str | None = None
    service_account: bool = False
