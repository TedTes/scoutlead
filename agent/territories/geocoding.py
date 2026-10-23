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
    country_code: str | None = None


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
        self._cache: dict[str, GeocodedMarket] = {}

    def resolve(self, location: str) -> GeocodedMarket | None:
        query = normalize_text(location)
        cache_key = query.casefold()
        if cache_key in self._cache:
            return self._cache[cache_key]

        # This small compatibility cache keeps existing audiences deterministic;
        # configured providers handle every location outside the original launch area.
        known = market_center(query)
        if known is not None:
            result = GeocodedMarket(known[0], known[1], query, "market_cache", country_code="ca")
            self._cache[cache_key] = result
            return result

        result = None
        if self.google_places_api_key:
            result = self._resolve_google(query)
        if result is None and self.openstreetmap_enabled:
            result = self._resolve_nominatim(query)
        # Provider failures are often transient. Cache only successful lookups so
        # one timeout does not make a city unresolvable until the process restarts.
        if result is not None:
            self._cache[cache_key] = result
        return result

    def search(self, location: str, *, limit: int = 5) -> list[GeocodedMarket]:
        query = normalize_text(location)
        if len(query) < 2:
            return []
        known = market_center(query)
        if known is not None:
            return [GeocodedMarket(known[0], known[1], query, "market_cache", country_code="ca")]
        results: list[GeocodedMarket] = []
        if self.google_places_api_key:
            results = self._search_google(query, limit=limit)
        if not results and self.openstreetmap_enabled:
            results = self._search_nominatim(query, limit=limit)
        results = results[:limit]
        for result in results:
            # A subsequent create/update request submits the canonical label shown
            # by autocomplete. Retaining it prevents a second provider search from
            # selecting a different similarly named place.
            self._cache[result.label.casefold()] = result
        return results

    def _resolve_google(self, query: str) -> GeocodedMarket | None:
        results = self._search_google(query, limit=1)
        return results[0] if results else None

    def _search_google(self, query: str, *, limit: int) -> list[GeocodedMarket]:
        try:
            response = httpx.post(
                self.google_places_endpoint,
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": self.google_places_api_key or "",
                    "X-Goog-FieldMask": (
                        "places.id,places.displayName,places.formattedAddress,"
                        "places.location,places.addressComponents"
                    ),
                },
                json={"textQuery": query, "pageSize": max(1, min(limit, 10))},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            places = response.json().get("places") or []
            results = []
            for place in places:
                coordinates = place.get("location") or {}
                latitude = coordinates.get("latitude")
                longitude = coordinates.get("longitude")
                if not coordinates_are_valid(latitude, longitude):
                    continue
                display_name = place.get("displayName") or {}
                components = place.get("addressComponents") or []
                country_code = next(
                    (
                        str(component.get("shortText") or "").lower()
                        for component in components
                        if "country" in (component.get("types") or [])
                    ),
                    None,
                )
                results.append(GeocodedMarket(
                    float(latitude),
                    float(longitude),
                    normalize_text(place.get("formattedAddress") or display_name.get("text") or query),
                    "google_places",
                    normalize_text(str(place.get("id") or "")) or None,
                    country_code,
                ))
            return results
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            logger.warning("Google market geocoding failed for %r: %s", query, exc)
            return []

    def _resolve_nominatim(self, query: str) -> GeocodedMarket | None:
        results = self._search_nominatim(query, limit=1)
        return results[0] if results else None

    def _search_nominatim(self, query: str, *, limit: int) -> list[GeocodedMarket]:
        try:
            response = httpx.get(
                self.nominatim_endpoint,
                params={
                    "q": query,
                    "format": "jsonv2",
                    "limit": max(1, min(limit, 10)),
                    "addressdetails": 1,
                },
                headers={"User-Agent": "ScoutLead audience-geocoder/1.0"},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            rows = response.json()
            if not isinstance(rows, list):
                return []
            results = []
            for row in rows:
                latitude = _float(row.get("lat"))
                longitude = _float(row.get("lon"))
                if not coordinates_are_valid(latitude, longitude):
                    continue
                address = row.get("address") or {}
                results.append(GeocodedMarket(
                    float(latitude),
                    float(longitude),
                    normalize_text(row.get("display_name") or query),
                    "openstreetmap_nominatim",
                    normalize_text(str(row.get("place_id") or "")) or None,
                    normalize_text(str(address.get("country_code") or "")).lower() or None,
                ))
            return results
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            logger.warning("Nominatim market geocoding failed for %r: %s", query, exc)
            return []


def _float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
