from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import MessageModel, ProductModel
from outreach_packages.playbooks import PlaybookCatalog, ServicePlaybook, load_playbook_catalog
from outreach_packages.schemas import (
    OutreachAnalyticsRead,
    OutreachDraftChannel,
    OutreachEventCreate,
    OutreachEventRead,
    PlaybookAdminRead,
)
from shared.errors import NotFoundError
from shared.utils import new_id, utcnow


class OutreachPlaybookRepository:
    """Read the application-owned playbook catalog.

    Database playbook overrides were removed. Reusable user-authored structure
    belongs in outreach_templates; strategy defaults remain versioned code.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def catalog(self) -> PlaybookCatalog:
        return load_playbook_catalog()

    def list(self) -> list[PlaybookAdminRead]:
        return sorted(
            (_playbook_read(service) for service in self.catalog().services),
            key=lambda item: item.service_key,
        )

    def get_row(self, service_key: str):
        return None

    def save(self, *, service_key: str, definition: dict[str, Any]):
        raise ValueError(
            "Database playbook overrides were retired; update the application catalog or an outreach template."
        )


class OutreachEventRepository:
    def __init__(self, session: Session, *, workspace_id: str | None) -> None:
        self.session = session
        self.workspace_id = workspace_id

    def record(self, package_id: str, event: OutreachEventCreate) -> OutreachEventRead:
        row = self._package(package_id)
        created_at = utcnow()
        event_row = {
            "id": new_id("outreach_event"),
            "package_id": package_id,
            "channel": event.channel,
            "event_type": event.event_type,
            "variant_id": event.variant_id,
            "metadata": event.metadata,
            "created_at": created_at.isoformat(),
        }
        context = dict(row.generation_context or {})
        context["events"] = [*(context.get("events") or []), event_row]
        row.generation_context = context
        if event.event_type == "message_sent":
            row.sent_at = created_at
        self.session.commit()
        return OutreachEventRead.model_validate(event_row)

    def sent_channels(self, package_id: str) -> dict[OutreachDraftChannel, datetime]:
        row = self._package(package_id)
        sent: dict[OutreachDraftChannel, datetime] = {}
        for event in reversed((row.generation_context or {}).get("events") or []):
            channel = event.get("channel")
            if event.get("event_type") != "message_sent" or channel not in {
                "instagram", "sms", "email", "call"
            }:
                continue
            value = event.get("created_at")
            if value:
                sent.setdefault(channel, datetime.fromisoformat(str(value)))
        return sent

    def analytics(self) -> OutreachAnalyticsRead:
        statement = select(MessageModel).where(MessageModel.channel == "outreach_package")
        if self.workspace_id:
            statement = statement.join(ProductModel).where(
                ProductModel.workspace_id == self.workspace_id
            )
        events = [
            event
            for row in self.session.scalars(statement)
            for event in ((row.generation_context or {}).get("events") or [])
        ]
        return OutreachAnalyticsRead(
            total_events=len(events),
            by_event=dict(Counter(str(event.get("event_type")) for event in events)),
            by_channel=dict(Counter(str(event.get("channel")) for event in events)),
            by_variant=dict(
                Counter(str(event.get("variant_id")) for event in events if event.get("variant_id"))
            ),
        )

    def _package(self, package_id: str) -> MessageModel:
        row = self.session.get(MessageModel, package_id)
        if row is None or row.channel != "outreach_package":
            raise NotFoundError("outreach package not found", {"package_id": package_id})
        if self.workspace_id:
            workspace_id = self.session.scalar(
                select(ProductModel.workspace_id).where(ProductModel.id == row.product_id)
            )
            if workspace_id != self.workspace_id:
                raise NotFoundError("outreach package not found", {"package_id": package_id})
        return row


def _playbook_read(service: ServicePlaybook) -> PlaybookAdminRead:
    return PlaybookAdminRead(
        id=None,
        service_key=service.service_key,
        version=service.version,
        status="default",
        definition=service.model_dump(),
        updated_at=None,
    )
