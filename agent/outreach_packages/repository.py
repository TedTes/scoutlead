from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import OutreachEventModel, OutreachPlaybookModel
from outreach_packages.playbooks import (
    PlaybookCatalog,
    ServicePlaybook,
    load_playbook_catalog,
)
from outreach_packages.schemas import (
    OutreachAnalyticsRead,
    OutreachEventCreate,
    OutreachEventRead,
    PlaybookAdminRead,
)
from shared.utils import new_id, utcnow


class OutreachPlaybookRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def catalog(self) -> PlaybookCatalog:
        default = load_playbook_catalog()
        overrides = self.session.scalars(
            select(OutreachPlaybookModel).where(OutreachPlaybookModel.status == "active")
        ).all()
        by_key = {service.service_key: service for service in default.services}
        for row in overrides:
            by_key[row.service_key] = ServicePlaybook.model_validate(row.definition)
        return default.model_copy(update={"services": list(by_key.values())})

    def list(self) -> list[PlaybookAdminRead]:
        default = load_playbook_catalog()
        rows = {
            row.service_key: row
            for row in self.session.scalars(
                select(OutreachPlaybookModel).order_by(OutreachPlaybookModel.service_key)
            ).all()
        }
        result: list[PlaybookAdminRead] = []
        for service in default.services:
            row = rows.pop(service.service_key, None)
            result.append(_playbook_read(row, service))
        for row in rows.values():
            result.append(_playbook_read(row, ServicePlaybook.model_validate(row.definition)))
        return sorted(result, key=lambda item: item.service_key)

    def get_row(self, service_key: str) -> OutreachPlaybookModel | None:
        return self.session.scalar(
            select(OutreachPlaybookModel).where(
                OutreachPlaybookModel.service_key == service_key
            )
        )

    def save(
        self,
        *,
        service_key: str,
        definition: dict[str, Any],
    ) -> OutreachPlaybookModel:
        validated = ServicePlaybook.model_validate(definition)
        if validated.service_key != service_key:
            raise ValueError("playbook service key does not match its route")
        row = self.get_row(service_key)
        if row is None:
            row = OutreachPlaybookModel(
                id=new_id("outreach_playbook"),
                service_key=service_key,
                version=1,
                status="draft",
                definition=validated.model_dump(),
            )
            self.session.add(row)
        else:
            row.version += 1
            row.status = "draft"
            row.definition = validated.model_dump()
        self.session.flush()
        return row


class OutreachEventRepository:
    def __init__(self, session: Session, *, workspace_id: str | None) -> None:
        self.session = session
        self.workspace_id = workspace_id

    def record(self, package_id: str, event: OutreachEventCreate) -> OutreachEventRead:
        row = OutreachEventModel(
            id=new_id("outreach_event"),
            workspace_id=self.workspace_id,
            package_id=package_id,
            channel=event.channel,
            event_type=event.event_type,
            variant_id=event.variant_id,
            event_metadata=event.metadata,
            created_at=utcnow(),
        )
        self.session.add(row)
        self.session.commit()
        return _event_read(row)

    def analytics(self) -> OutreachAnalyticsRead:
        rows = self.session.scalars(
            select(OutreachEventModel).where(
                OutreachEventModel.workspace_id == self.workspace_id
            )
        ).all()
        return OutreachAnalyticsRead(
            total_events=len(rows),
            by_event=dict(Counter(row.event_type for row in rows)),
            by_channel=dict(Counter(row.channel for row in rows)),
            by_variant=dict(Counter(row.variant_id for row in rows if row.variant_id)),
        )


def _playbook_read(
    row: OutreachPlaybookModel | None,
    service: ServicePlaybook,
) -> PlaybookAdminRead:
    return PlaybookAdminRead(
        id=row.id if row else None,
        service_key=service.service_key,
        version=row.version if row else service.version,
        status=row.status if row else "default",
        definition=(row.definition if row else service.model_dump()),
        updated_at=row.updated_at if row else None,
    )


def _event_read(row: OutreachEventModel) -> OutreachEventRead:
    return OutreachEventRead(
        id=row.id,
        package_id=row.package_id,
        channel=row.channel,
        event_type=row.event_type,
        variant_id=row.variant_id,
        metadata=row.event_metadata,
        created_at=row.created_at,
    )
