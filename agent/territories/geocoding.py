from __future__ import annotations

from dataclasses import dataclass
import logging

import httpx

from shared.geospatial import coordinates_are_valid
from shared.utils import normalize_text
from territories.markets import market_center


DEFAULT_GOOGLE_PLACES_ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
DEFAULT_NOMINATIM_ENDPOINT = "https://nominatim.openstreetmap.org/search"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GeocodedMarket:
    latitude: float
    longitude: float
    label: str
    provider: str
    external_id: str | None = None


class MarketGeocoder:
    """Resolve audience labels to a center without making geography part of identity."""

    def __init__(
        self,
        *,
        google_places_api_key: str | None = None,
        google_places_endpoint: str | None = None,
        openstreetmap_enabled: bool = True,
        nominatim_endpoint: str | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.google_places_api_key = google_places_api_key
        self.google_places_endpoint = (
            google_places_endpoint or DEFAULT_GOOGLE_PLACES_ENDPOINT
        )
        self.openstreetmap_enabled = openstreetmap_enabled
        self.nominatim_endpoint = nominatim_endpoint or DEFAULT_NOMINATIM_ENDPOINT
        self.timeout_seconds = timeout_seconds
        self._cache: dict[str, GeocodedMarket | None] = {}

    def resolve(self, location: str) -> GeocodedMarket | None:
        query = normalize_text(location)
        cache_key = query.casefold()
        if cache_key in self._cache:
            return self._cache[cache_key]

        # This small compatibility cache keeps existing audiences deterministic;
        # configured providers handle every location outside the original launch area.
        known = market_center(query)
        if known is not None:
            result = GeocodedMarket(known[0], known[1], query, "market_cache")
            self._cache[cache_key] = result
            return result

        result = None
        if self.google_places_api_key:
            result = self._resolve_google(query)
        if result is None and self.openstreetmap_enabled:
            result = self._resolve_nominatim(query)
        self._cache[cache_key] = result
        return result

    def _resolve_google(self, query: str) -> GeocodedMarket | None:
        try:
            response = httpx.post(
                self.google_places_endpoint,
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": self.google_places_api_key or "",
                    "X-Goog-FieldMask": (
                        "places.id,places.displayName,places.formattedAddress,places.location"
                    ),
                },
                json={"textQuery": query, "pageSize": 1},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            places = response.json().get("places") or []
            if not places:
                return None
            place = places[0]
            coordinates = place.get("location") or {}
            latitude = coordinates.get("latitude")
            longitude = coordinates.get("longitude")
            if not coordinates_are_valid(latitude, longitude):
                return None
            display_name = place.get("displayName") or {}
            label = normalize_text(
                place.get("formattedAddress") or display_name.get("text") or query
            )
            return GeocodedMarket(
                float(latitude),
                float(longitude),
                label,
                "google_places",
                normalize_text(str(place.get("id") or "")) or None,
            )
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            logger.warning("Google market geocoding failed for %r: %s", query, exc)
            return None

    def _resolve_nominatim(self, query: str) -> GeocodedMarket | None:
        try:
            response = httpx.get(
                self.nominatim_endpoint,
                params={
                    "q": query,
                    "format": "jsonv2",
                    "limit": 1,
                    "addressdetails": 1,
                },
                headers={"User-Agent": "ScoutLead audience-geocoder/1.0"},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            rows = response.json()
            if not isinstance(rows, list) or not rows:
                return None
            row = rows[0]
            latitude = _float(row.get("lat"))
            longitude = _float(row.get("lon"))
            if not coordinates_are_valid(latitude, longitude):
                return None
            return GeocodedMarket(
                float(latitude),
                float(longitude),
                normalize_text(row.get("display_name") or query),
                "openstreetmap_nominatim",
                normalize_text(str(row.get("place_id") or "")) or None,
            )
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            logger.warning("Nominatim market geocoding failed for %r: %s", query, exc)
            return None


def _float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
