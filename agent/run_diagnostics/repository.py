from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import RunPipelineEventModel
from shared.utils import new_id


class RunPipelineEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        campaign_id: str,
        stage: str,
        event_type: str,
        status: str,
        segment_id: str | None = None,
        job_id: str | None = None,
        provider_id: str | None = None,
        business_id: str | None = None,
        lead_id: str | None = None,
        item_key: str | None = None,
        request_payload: dict[str, Any] | None = None,
        response_payload: dict[str, Any] | None = None,
        reason: str | None = None,
        commit: bool = True,
    ) -> RunPipelineEventModel:
        event = RunPipelineEventModel(
            id=new_id("pipeline_event"),
            campaign_id=campaign_id,
            segment_id=segment_id,
            job_id=job_id,
            stage=stage,
            event_type=event_type,
            status=status,
            provider_id=provider_id,
            business_id=business_id,
            lead_id=lead_id,
            item_key=item_key,
            request_payload=request_payload,
            response_payload=response_payload,
            reason=reason,
        )
        self.session.add(event)
        if commit:
            self.session.commit()
            self.session.refresh(event)
        else:
            self.session.flush()
        return event

    def list_by_campaign(self, campaign_id: str) -> list[RunPipelineEventModel]:
        return list(
            self.session.scalars(
                select(RunPipelineEventModel)
                .where(RunPipelineEventModel.campaign_id == campaign_id)
                .order_by(RunPipelineEventModel.created_at, RunPipelineEventModel.id)
            )
        )
