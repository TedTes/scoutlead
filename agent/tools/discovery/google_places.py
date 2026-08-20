from __future__ import annotations

from typing import Any

import httpx

from campaign_sources.schemas import CampaignSourceRead
from campaigns.schemas import CampaignRead
from products.schemas import ProductRead
from shared.errors import ConfigurationError
from tools.base import ToolResult, ToolSlot, measured_tool_result
from tools.search import SearchResult


DEFAULT_GOOGLE_PLACES_ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
GOOGLE_PLACES_FIELD_MASK = ",".join(
    [
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
        query = self._query(source=source, product=product)
        limit = int(source.config.get("limit") or campaign.max_leads)
        page_size = max(1, min(limit, 20))

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
            request_body["strictTypeFiltering"] = bool(source.config.get("strict_type_filtering", False))
        region_code = source.config.get("region_code")
        if region_code:
            request_body["regionCode"] = str(region_code)

        def action() -> list[dict[str, Any]]:
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
                json=request_body,
            )
            response.raise_for_status()
            places = response.json().get("places", [])
            return [
                self._to_search_result(place=place, query=query).model_dump(mode="json")
                for place in places[:limit]
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
                "request": request_body,
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
        if geography and not _is_broad_geography(geography) and geography.lower() not in query.lower():
            return f"{query} {geography}"
        return query

    @staticmethod
    def _to_search_result(*, place: dict[str, Any], query: str) -> SearchResult:
        display_name = place.get("displayName") or {}
        title = str(display_name.get("text") or place.get("id") or query)
        website_url = place.get("websiteUri")
        maps_url = place.get("googleMapsUri")
        url = website_url or maps_url
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
            url=url,
            snippet=" | ".join(snippet_parts) or None,
            geography=address,
            source="google_places",
            raw={**place, "query": query, "website_url": website_url, "google_maps_url": maps_url},
        )


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
