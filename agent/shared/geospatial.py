from __future__ import annotations

import math
from typing import Any

from sqlalchemy import case, func, literal


EARTH_RADIUS_KM = 6371.0088


def coordinates_are_valid(latitude: object, longitude: object) -> bool:
    return (
        isinstance(latitude, int | float)
        and not isinstance(latitude, bool)
        and isinstance(longitude, int | float)
        and not isinstance(longitude, bool)
        and math.isfinite(float(latitude))
        and math.isfinite(float(longitude))
        and -90 <= float(latitude) <= 90
        and -180 <= float(longitude) <= 180
    )


def haversine_distance_km(
    first_latitude: float,
    first_longitude: float,
    second_latitude: float,
    second_longitude: float,
) -> float:
    """Return great-circle distance between two WGS84 coordinate pairs."""
    first_latitude_radians = math.radians(first_latitude)
    second_latitude_radians = math.radians(second_latitude)
    latitude_delta = math.radians(second_latitude - first_latitude)
    longitude_delta = math.radians(second_longitude - first_longitude)
    haversine = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(first_latitude_radians)
        * math.cos(second_latitude_radians)
        * math.sin(longitude_delta / 2) ** 2
    )
    haversine = min(1.0, max(0.0, haversine))
    return EARTH_RADIUS_KM * 2 * math.atan2(
        math.sqrt(haversine),
        math.sqrt(1 - haversine),
    )


def haversine_distance_km_expression(
    *,
    center_latitude: float,
    center_longitude: float,
    latitude: Any,
    longitude: Any,
):
    """Build a portable SQL Haversine expression for PostgreSQL and SQLite."""
    latitude_delta = func.radians(latitude - literal(center_latitude))
    longitude_delta = func.radians(longitude - literal(center_longitude))
    center_latitude_radians = func.radians(literal(center_latitude))
    latitude_radians = func.radians(latitude)
    latitude_sine = func.sin(latitude_delta / 2.0)
    longitude_sine = func.sin(longitude_delta / 2.0)
    haversine = (
        latitude_sine * latitude_sine
        + func.cos(center_latitude_radians)
        * func.cos(latitude_radians)
        * longitude_sine
        * longitude_sine
    )
    bounded_haversine = case(
        (haversine < 0.0, 0.0),
        (haversine > 1.0, 1.0),
        else_=haversine,
    )
    # atan2 avoids the precision problems of acos for very short distances.
    return literal(2.0 * EARTH_RADIUS_KM) * func.atan2(
        func.sqrt(bounded_haversine),
        func.sqrt(1.0 - bounded_haversine),
    )
