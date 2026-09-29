from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import CampaignModel, LeadModel


def exclude_previously_delivered_rows(
    session: Session,
    *,
    campaign_id: str,
    product_id: str,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    campaign = session.get(CampaignModel, campaign_id)
    if campaign is None or not campaign.territory_id:
        return rows
    delivered_ids = set(
        session.scalars(
            select(LeadModel.business_id)
            .join(CampaignModel, LeadModel.campaign_id == CampaignModel.id)
            .where(
                LeadModel.product_id == product_id,
                LeadModel.business_id.is_not(None),
                CampaignModel.territory_id.is_not(None),
                CampaignModel.id != campaign_id,
            )
        )
    )
    if not delivered_ids:
        return rows
    return [row for row in rows if _canonical_business_id(row) not in delivered_ids]


def _canonical_business_id(row: dict[str, Any]) -> str | None:
    current: Any = row
    while isinstance(current, dict):
        value = current.get("canonical_business_id")
        if isinstance(value, str) and value:
            return value
        current = current.get("raw")
    return None
