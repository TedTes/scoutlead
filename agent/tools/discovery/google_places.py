from __future__ import annotations

import math
from typing import Any

import httpx

from campaign_sources.schemas import CampaignSourceRead
from campaigns.schemas import CampaignRead
from canonical.normalization import normalize_business_name, normalize_phone
from products.schemas import ProductRead
from shared.errors import ConfigurationError
from tools.base import ToolResult, ToolSlot, measured_tool_result
from tools.search import SearchResult


DEFAULT_GOOGLE_PLACES_ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
GOOGLE_PLACES_FIELD_MASK = ",".join(
    [
        "nextPageToken",
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.nationalPhoneNumber",
        "places.websiteUri",
        "places.googleMapsUri",
        "places.businessStatus",
        "places.rating",
        "places.userRatingCount",
        "places.types",
    ]
)


class GooglePlacesDiscoveryAdapter:
    provider_id = "google_places"

    def __init__(
        self,
        *,
        api_key: str | None,
        endpoint: str | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.api_key = api_key
        self.endpoint = endpoint or DEFAULT_GOOGLE_PLACES_ENDPOINT
        self.timeout_seconds = timeout_seconds

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def run(self, source: CampaignSourceRead, context: dict[str, Any]) -> ToolResult:
        if not self.is_configured:
            raise ConfigurationError(
                "GOOGLE_PLACES_API_KEY is required for google_places campaign sources",
                {"campaign_source_id": source.id, "provider_id": self.provider_id},
            )

        product = ProductRead.model_validate(context["product"])
        campaign = CampaignRead.model_validate(context["campaign"])
        queries = self._queries(source=source, product=product)
        query = queries[0]
        limit = int(source.config.get("limit") or campaign.max_leads)
        page_size = max(1, min(math.ceil(limit / len(queries)), 20))
        website_policy = str(
            source.config.get("website_policy")
            or source.input.get("website_policy")
            or "any"
        )

        request_body: dict[str, Any] = {
            "textQuery": query,
            "pageSize": page_size,
            "includePureServiceAreaBusinesses": bool(
                source.config.get("include_pure_service_area_businesses", True)
            ),
        }
        included_type = source.config.get("included_type")
        if included_type:
            request_body["includedType"] = str(included_type)
            request_body["strictTypeFiltering"] = bool(
                source.config.get("strict_type_filtering", False)
            )
        region_code = source.config.get("region_code")
        if region_code:
            request_body["regionCode"] = str(region_code)

        def action() -> list[dict[str, Any]]:
            places: list[tuple[dict[str, Any], str]] = []
            seen_place_keys: set[str] = set()
            continuations: list[tuple[str, str]] = []

            def fetch_page(
                search_query: str,
                *,
                size: int,
                page_token: str | None = None,
            ) -> str | None:
                page_body = dict(request_body)
                page_body["textQuery"] = search_query
                page_body["pageSize"] = size
                if page_token:
                    page_body["pageToken"] = page_token
                response = httpx.post(
                    self.endpoint,
                    timeout=self.timeout_seconds,
                    headers={
                        "Content-Type": "application/json",
                        "X-Goog-Api-Key": self.api_key or "",
                        "X-Goog-FieldMask": str(
                            source.config.get("field_mask") or GOOGLE_PLACES_FIELD_MASK
                        ),
                    },
                    json=page_body,
                )
                response.raise_for_status()
                payload = response.json()
                for place in payload.get("places", []):
                    if not self._matches_website_policy(place, website_policy):
                        continue
                    place_keys = self._place_keys(place)
                    if place_keys & seen_place_keys:
                        continue
                    seen_place_keys.update(place_keys)
                    places.append((place, search_query))
                token = payload.get("nextPageToken")
                return str(token) if token else None

            for search_query in queries:
                token = fetch_page(search_query, size=page_size)
                if token:
                    continuations.append((search_query, token))

            seen_tokens: set[tuple[str, str]] = set()
            while len(places) < limit and continuations:
                search_query, token = continuations.pop(0)
                token_key = (search_query, token)
                if token_key in seen_tokens:
                    continue
                seen_tokens.add(token_key)
                next_token = fetch_page(
                    search_query,
                    size=min(20, limit - len(places)),
                    page_token=token,
                )
                if next_token:
                    continuations.append((search_query, next_token))
            if website_policy == "missing_or_unavailable":
                places.sort(key=lambda item: bool(item[0].get("websiteUri")))
            return [
                self._to_search_result(
                    place=place,
                    query=search_query,
                    website_policy=website_policy,
                ).model_dump(mode="json")
                for place, search_query in places[:limit]
            ]

        return measured_tool_result(
            provider=self.provider_id,
            slot=ToolSlot.DISCOVERY,
            confidence=90,
            source_urls=[],
            raw={
                "campaign_source_id": source.id,
                "provider_id": source.provider_id,
                "input": source.input,
                "config": source.config,
                "request": {**request_body, "queries": queries},
            },
            action=action,
        )

    @staticmethod
    def _query(*, source: CampaignSourceRead, product: ProductRead) -> str:
        query = str(source.input.get("query") or "").strip()
        if not query:
            raise ConfigurationError(
                "google_places source query is empty",
                {"campaign_source_id": source.id, "provider_id": source.provider_id},
            )
        geography = str(source.input.get("geography") or product.target_geography or "").strip()
        if (
            geography
            and not _is_broad_geography(geography)
            and geography.lower() not in query.lower()
        ):
            return f"{query} {geography}"
        return query

    @classmethod
    def _queries(cls, *, source: CampaignSourceRead, product: ProductRead) -> list[str]:
        configured = source.config.get("search_queries") or source.input.get("search_queries")
        if isinstance(configured, list):
            queries = [str(item).strip() for item in configured if str(item).strip()]
            if queries:
                return list(dict.fromkeys(queries))
        return [cls._query(source=source, product=product)]

    @staticmethod
    def _to_search_result(
        *,
        place: dict[str, Any],
        query: str,
        website_policy: str = "any",
    ) -> SearchResult:
        display_name = place.get("displayName") or {}
        title = str(display_name.get("text") or place.get("id") or query)
        website_url = place.get("websiteUri")
        maps_url = place.get("googleMapsUri")
        address = place.get("formattedAddress")
        phone = place.get("nationalPhoneNumber")
        rating = place.get("rating")
        review_count = place.get("userRatingCount")
        types = place.get("types") or []
        snippet_parts = [
            part
            for part in [
                address,
                f"phone: {phone}" if phone else None,
                f"rating: {rating}" if rating is not None else None,
                f"reviews: {review_count}" if review_count is not None else None,
                ", ".join(types[:5]) if types else None,
            ]
            if part
        ]
        return SearchResult(
            title=title,
            url=website_url,
            snippet=" | ".join(snippet_parts) or None,
            geography=address,
            source="google_places",
            raw={
                **place,
                "query": query,
                "website_url": website_url,
                "google_maps_url": maps_url,
                **(
                    {
                        "website_presence_status": "no_website_listed",
                        "website_presence_label": "No website listed",
                    }
                    if website_policy in {"missing", "missing_or_unavailable"}
                    and not website_url
                    else {}
                ),
            },
        )

    @staticmethod
    def _matches_website_policy(place: dict[str, Any], website_policy: str) -> bool:
        if website_policy not in {"missing", "missing_or_unavailable"}:
            return True
        reachable_business = bool(
            place.get("businessStatus") == "OPERATIONAL"
            and (place.get("nationalPhoneNumber") or place.get("googleMapsUri"))
        )
        if website_policy == "missing":
            return reachable_business and not place.get("websiteUri")
        return reachable_business

    @staticmethod
    def _place_keys(place: dict[str, Any]) -> set[str]:
        keys: set[str] = set()
        place_id = str(place.get("id") or "").strip()
        if place_id:
            keys.add(f"id:{place_id}")
        display_name = place.get("displayName") or {}
        name = normalize_business_name(str(display_name.get("text") or ""))
        address = " ".join(
            str(place.get("formattedAddress") or "").lower().replace(",", " ").split()
        )
        phone = normalize_phone(place.get("nationalPhoneNumber"))
        if name and phone:
            keys.add(f"name-phone:{name}|{phone}")
        if name and address:
            keys.add(f"name-address:{name}|{address}")
        if not keys:
            keys.add(f"fallback:{name}|{address}|{phone or ''}")
        return keys


def _is_broad_geography(value: str) -> bool:
    normalized = value.lower().replace("&", "and")
    broad_terms = {
        "united states",
        "usa",
        "us",
        "canada",
        "north america",
        "united states, canada",
        "united states and canada",
    }
    return normalized in broad_terms
