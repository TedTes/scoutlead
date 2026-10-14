from __future__ import annotations

from db.models import BusinessModel


def searchable_business_conditions() -> list:
    """Return structural conditions for a business with an active scoped membership."""
    return [BusinessModel.status == "active"]
