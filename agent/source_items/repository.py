from __future__ import annotations

import hashlib
import json

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from db.models import SourceItemDecisionModel, SourceItemModel
from shared.errors import NotFoundError
from shared.utils import new_id
from source_items.schemas import (
    SourceItemCreate,
    SourceItemDecisionCreate,
    SourceItemState,
)


class SourceItemRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def ingest(self, value: SourceItemCreate, *, commit: bool = True) -> SourceItemModel:
        content_hash = source_item_content_hash(value)
        item = SourceItemModel(
            id=new_id("source_item"),
            **value.model_dump(),
            content_hash=content_hash,
            state=SourceItemState.FETCHED.value,
        )
        self.session.add(item)
        self._finish(item, commit=commit)
        return item

    def add_decision(
        self,
        source_item_id: str,
        value: SourceItemDecisionCreate,
        *,
        next_state: SourceItemState,
        business_id: str | None = None,
        error: str | None = None,
        commit: bool = True,
    ) -> SourceItemDecisionModel:
        item = self.get(source_item_id)
        decision = SourceItemDecisionModel(
            id=new_id("source_decision"),
            source_item_id=item.id,
            **value.model_dump(mode="json"),
        )
        item.state = next_state.value
        if business_id is not None:
            item.business_id = business_id
        item.last_error = error
        self.session.add(decision)
        self._finish(decision, commit=commit)
        return decision

    def get(self, source_item_id: str) -> SourceItemModel:
        item = self.session.get(SourceItemModel, source_item_id)
        if item is None:
            raise NotFoundError("source item not found", {"source_item_id": source_item_id})
        return item

    def latest_user_decision_for(self, item: SourceItemModel) -> SourceItemDecisionModel | None:
        identity_filters = [SourceItemModel.content_hash == item.content_hash]
        if item.external_id:
            identity_filters.append(SourceItemModel.external_id == item.external_id)
        if item.source_url:
            identity_filters.append(SourceItemModel.source_url == item.source_url)
        return self.session.scalar(
            select(SourceItemDecisionModel)
            .join(SourceItemModel, SourceItemModel.id == SourceItemDecisionModel.source_item_id)
            .where(
                SourceItemModel.id != item.id,
                SourceItemModel.segment_id == item.segment_id,
                SourceItemModel.provider_id == item.provider_id,
                SourceItemDecisionModel.actor_type == "user",
                SourceItemDecisionModel.decision.in_(
                    [
                        "accepted",
                        "rejected",
                        "duplicate",
                    ]
                ),
                or_(*identity_filters),
            )
            .order_by(SourceItemDecisionModel.created_at.desc())
            .limit(1)
        )

    def list_for_segment(
        self,
        segment_id: str,
        *,
        state: SourceItemState | None = None,
        limit: int = 100,
    ) -> list[SourceItemModel]:
        statement = select(SourceItemModel).where(SourceItemModel.segment_id == segment_id)
        if state is not None:
            statement = statement.where(SourceItemModel.state == state.value)
        return list(
            self.session.scalars(
                statement.order_by(SourceItemModel.fetched_at.desc()).limit(limit)
            )
        )

    def _finish(self, model, *, commit: bool) -> None:
        if commit:
            self.session.commit()
            self.session.refresh(model)
        else:
            self.session.flush()


def source_item_content_hash(value: SourceItemCreate) -> str:
    stable_payload = {
        "external_id": value.external_id,
        "query": value.query,
        "source_url": value.source_url,
        "title": value.title,
        "raw_payload": value.raw_payload,
    }
    encoded = json.dumps(
        stable_payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
