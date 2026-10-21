from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from canonical.attributes import extract_business_attributes
from db.models import BusinessModel, SourceObservationModel, TerritoryModel
from shared.geospatial import coordinates_are_valid, haversine_distance_km
from territories.geocoding import MarketGeocoder


@dataclass
class CoordinateBackfillSummary:
    dry_run: bool
    audiences_scanned: int = 0
    audiences_backfilled: int = 0
    audiences_unresolved: int = 0
    businesses_scanned: int = 0
    businesses_backfilled: int = 0
    businesses_unresolved: int = 0
    business_coordinate_conflicts: int = 0
    invalid_business_coordinates: int = 0

    def as_dict(self) -> dict[str, int | bool]:
        return asdict(self)


class CoordinateBackfillService:
    def __init__(self, session: Session, *, geocoder: MarketGeocoder) -> None:
        self.session = session
        self.geocoder = geocoder

    def run(self, *, dry_run: bool = True, limit: int | None = None) -> CoordinateBackfillSummary:
        summary = CoordinateBackfillSummary(dry_run=dry_run)
        self._backfill_audiences(summary, limit=limit)
        self._backfill_businesses(summary, limit=limit)
        if dry_run:
            self.session.rollback()
        else:
            self.session.commit()
        return summary

    def _backfill_audiences(
        self,
        summary: CoordinateBackfillSummary,
        *,
        limit: int | None,
    ) -> None:
        statement = (
            select(TerritoryModel)
            .where(
                TerritoryModel.status != "archived",
                or_(
                    TerritoryModel.latitude.is_(None),
                    TerritoryModel.longitude.is_(None),
                    TerritoryModel.latitude < -90,
                    TerritoryModel.latitude > 90,
                    TerritoryModel.longitude < -180,
                    TerritoryModel.longitude > 180,
                ),
            )
            .order_by(TerritoryModel.created_at)
        )
        if limit is not None:
            statement = statement.limit(limit)
        for audience in self.session.scalars(statement):
            if coordinates_are_valid(audience.latitude, audience.longitude):
                continue
            summary.audiences_scanned += 1
            resolved = self.geocoder.resolve(audience.city or audience.market_key)
            if resolved is None:
                summary.audiences_unresolved += 1
                continue
            summary.audiences_backfilled += 1
            audience.latitude = resolved.latitude
            audience.longitude = resolved.longitude

    def _backfill_businesses(
        self,
        summary: CoordinateBackfillSummary,
        *,
        limit: int | None,
    ) -> None:
        statement = (
            select(BusinessModel)
            .where(
                or_(
                    BusinessModel.latitude.is_(None),
                    BusinessModel.longitude.is_(None),
                    BusinessModel.latitude < -90,
                    BusinessModel.latitude > 90,
                    BusinessModel.longitude < -180,
                    BusinessModel.longitude > 180,
                )
            )
            .order_by(BusinessModel.created_at)
        )
        if limit is not None:
            statement = statement.limit(limit)
        for business in self.session.scalars(statement):
            if coordinates_are_valid(business.latitude, business.longitude):
                continue
            summary.businesses_scanned += 1
            if business.latitude is not None or business.longitude is not None:
                summary.invalid_business_coordinates += 1
            observations = list(
                self.session.scalars(
                    select(SourceObservationModel)
                    .where(SourceObservationModel.business_id == business.id)
                    .order_by(SourceObservationModel.observed_at.desc())
                )
            )
            coordinate_candidates = [
                (attributes.latitude, attributes.longitude)
                for attributes in (
                    extract_business_attributes(
                        [observation.raw_payload],
                        category=business.category_key,
                    )
                    for observation in observations
                )
                if coordinates_are_valid(attributes.latitude, attributes.longitude)
            ]
            if _coordinates_conflict(coordinate_candidates):
                summary.business_coordinate_conflicts += 1
                continue
            attributes = extract_business_attributes(
                [observation.raw_payload for observation in observations],
                category=business.category_key,
            )
            if not coordinates_are_valid(attributes.latitude, attributes.longitude):
                summary.businesses_unresolved += 1
                continue
            summary.businesses_backfilled += 1
            business.latitude = attributes.latitude
            business.longitude = attributes.longitude


def _coordinates_conflict(
    coordinates: list[tuple[float | None, float | None]],
    *,
    tolerance_km: float = 1.0,
) -> bool:
    if len(coordinates) < 2:
        return False
    first_latitude, first_longitude = coordinates[0]
    if first_latitude is None or first_longitude is None:
        return False
    return any(
        latitude is not None
        and longitude is not None
        and haversine_distance_km(
            first_latitude,
            first_longitude,
            latitude,
            longitude,
        )
        > tolerance_km
        for latitude, longitude in coordinates[1:]
    )
