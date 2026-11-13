from typing import Any

from sqlalchemy import true
from sqlalchemy.orm import Session

from db.models import BusinessAttributeModel


def active_membership_condition():
    """All memberships are active; batch lifecycle is no longer persisted."""
    return true()


def observation_is_quarantined(
    session: Session,
    observation: BusinessAttributeModel,
) -> bool:
    return False


def observation_batch_id(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = str(payload.get("seed_batch_id") or "").strip()
    return value or None
