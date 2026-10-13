from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from db.models import ServiceDefinitionModel, ServiceSignalMappingModel


class ServiceDefinitionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, service_id: str) -> ServiceDefinitionModel | None:
        return self.session.scalar(
            select(ServiceDefinitionModel)
            .where(ServiceDefinitionModel.id == service_id)
            .options(
                selectinload(ServiceDefinitionModel.signal_mappings).selectinload(
                    ServiceSignalMappingModel.signal_definition
                )
            )
        )

    def get_by_key(self, key: str) -> ServiceDefinitionModel | None:
        return self.session.scalar(
            select(ServiceDefinitionModel)
            .where(ServiceDefinitionModel.key == key)
            .options(
                selectinload(ServiceDefinitionModel.signal_mappings).selectinload(
                    ServiceSignalMappingModel.signal_definition
                )
            )
        )

    def list(self, *, status: str | None = None) -> list[ServiceDefinitionModel]:
        statement = select(ServiceDefinitionModel).options(
            selectinload(ServiceDefinitionModel.signal_mappings).selectinload(
                ServiceSignalMappingModel.signal_definition
            )
        )
        if status:
            statement = statement.where(ServiceDefinitionModel.status == status)
        return list(
            self.session.scalars(
                statement.order_by(
                    ServiceDefinitionModel.sort_order,
                    ServiceDefinitionModel.label,
                )
            ).unique()
        )

    def signal_keys(self, service_keys: list[str]) -> list[str]:
        if not service_keys:
            return []
        services = self.session.scalars(
            select(ServiceDefinitionModel)
            .where(
                ServiceDefinitionModel.key.in_(service_keys),
                ServiceDefinitionModel.status == "active",
            )
            .options(
                selectinload(ServiceDefinitionModel.signal_mappings).selectinload(
                    ServiceSignalMappingModel.signal_definition
                )
            )
        ).unique()
        mapped: list[tuple[int, int, str]] = []
        for service in services:
            for mapping in service.signal_mappings:
                signal = mapping.signal_definition
                if signal.status == "active" and signal.opportunity_direction != "none":
                    mapped.append((service.sort_order, mapping.sort_order, signal.key))
        return list(dict.fromkeys(key for _, _, key in sorted(mapped)))
