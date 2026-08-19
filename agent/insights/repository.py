from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import CampaignInsightModel
from insights.schemas import CampaignInsightDraft
from shared.utils import new_id


class CampaignInsightRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        campaign_id: str,
        product_id: str,
        goal_type: str,
        draft: CampaignInsightDraft,
        metrics_snapshot: dict,
    ) -> CampaignInsightModel:
        model = CampaignInsightModel(
            id=new_id("insight"),
            campaign_id=campaign_id,
            product_id=product_id,
            goal_type=goal_type,
            summary=draft.summary,
            findings=[finding.model_dump(mode="json") for finding in draft.findings],
            icp_verdict=draft.icp_verdict.model_dump(mode="json"),
            metrics_snapshot=metrics_snapshot,
            evidence=draft.evidence,
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return model

    def latest_for_campaign(self, campaign_id: str) -> CampaignInsightModel | None:
        return self.session.scalar(
            select(CampaignInsightModel)
            .where(CampaignInsightModel.campaign_id == campaign_id)
            .order_by(CampaignInsightModel.created_at.desc())
            .limit(1)
        )
