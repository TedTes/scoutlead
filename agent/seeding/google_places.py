from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Iterable

import httpx

from canonical.normalization import normalize_business_name, normalize_domain, normalize_phone
from seeding.schemas import BusinessSeedInput
from shared.utils import normalize_text, normalize_url
from tools.discovery.google_places import DEFAULT_GOOGLE_PLACES_ENDPOINT


GOOGLE_PLACES_SEED_FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.nationalPhoneNumber",
        "places.internationalPhoneNumber",
        "places.websiteUri",
        "places.googleMapsUri",
        "places.businessStatus",
        "places.rating",
        "places.userRatingCount",
        "places.types",
        "nextPageToken",
    ]
)


PAINTING_SERVICE_QUERIES = [
    "residential painters {city}",
    "house painters {city}",
    "painting contractors {city}",
    "interior painters {city}",
    "exterior painters {city}",
    "cabinet painters {city}",
]

NICHE_QUERY_TEMPLATES = {
    "home_service_painting": PAINTING_SERVICE_QUERIES,
    "home_service_roofing": [
        "roofing contractors {city}",
        "residential roofers {city}",
        "roof repair companies {city}",
    ],
    "home_service_hvac": [
        "HVAC contractors {city}",
        "heating and cooling companies {city}",
        "furnace and air conditioning service {city}",
    ],
    "home_service_landscaping": [
        "landscaping companies {city}",
        "residential landscapers {city}",
        "lawn care services {city}",
    ],
    "home_service_cleaning": [
        "house cleaning companies {city}",
        "residential cleaning services {city}",
        "home cleaners {city}",
    ],
}

NICHE_INCLUDED_TYPES = {
    "home_service_painting": "painter",
    "home_service_roofing": "roofing_contractor",
    "home_service_hvac": "hvac_contractor",
    "home_service_landscaping": "landscaper",
    "home_service_cleaning": "cleaning_service",
}


TORONTO_GTA_SEED_CITIES = [
    "Toronto ON",
    "North York ON",
    "Scarborough ON",
    "Etobicoke ON",
    "East York ON",
    "York ON",
    "Mississauga ON",
    "Brampton ON",
    "Vaughan ON",
    "Markham ON",
    "Richmond Hill ON",
    "Thornhill ON",
    "Woodbridge ON",
    "Maple ON",
    "Concord ON",
    "Oakville ON",
    "Burlington ON",
    "Milton ON",
    "Pickering ON",
    "Ajax ON",
    "Whitby ON",
    "Oshawa ON",
    "Courtice ON",
    "Bowmanville ON",
    "Newmarket ON",
    "Aurora ON",
    "Stouffville ON",
    "King City ON",
    "Nobleton ON",
    "Bolton ON",
    "Caledon ON",
    "Georgetown ON",
    "Uxbridge ON",
    "Port Perry ON",
]


@dataclass(frozen=True)
class GooglePlacesSeedQuery:
    text_query: str
    seed_market: str
    region_code: str | None = "CA"
    included_type: str | None = "painter"
    strict_type_filtering: bool = False
    include_pure_service_area_businesses: bool = True
    seed_niche: str = "home_service_painting"


@dataclass(frozen=True)
class GooglePlacesSeedCollection:
    rows: list[BusinessSeedInput]
    requests_made: int
    queries_attempted: int


class GooglePlacesSeedCollector:
    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str | None = None,
        timeout_seconds: float = 20.0,
        page_delay_seconds: float = 0.5,
    ) -> None:
        self.api_key = api_key
        self.endpoint = endpoint or DEFAULT_GOOGLE_PLACES_ENDPOINT
        self.timeout_seconds = timeout_seconds
        self.page_delay_seconds = max(0.0, page_delay_seconds)

    def collect(
        self,
        queries: Iterable[GooglePlacesSeedQuery],
        *,
        target_count: int,
        existing: Iterable[BusinessSeedInput] = (),
        max_requests: int | None = None,
        max_pages_per_query: int = 3,
    ) -> GooglePlacesSeedCollection:
        rows = list(existing)
        seen = {seed_dedupe_key(row) for row in rows if seed_dedupe_key(row)}
        requests_made = 0
        queries_attempted = 0

        for query in queries:
            if len(rows) >= target_count:
                break
            if max_requests is not None and requests_made >= max_requests:
                break
            queries_attempted += 1
            page_token: str | None = None
            pages_loaded = 0

            while len(rows) < target_count and pages_loaded < max_pages_per_query:
                if max_requests is not None and requests_made >= max_requests:
                    break
                payload = _request_payload(query, page_token=page_token)
                response = httpx.post(
                    self.endpoint,
                    timeout=self.timeout_seconds,
                    headers={
                        "Content-Type": "application/json",
                        "X-Goog-Api-Key": self.api_key,
                        "X-Goog-FieldMask": GOOGLE_PLACES_SEED_FIELD_MASK,
                    },
                    json=payload,
                )
                requests_made += 1
                pages_loaded += 1
                response.raise_for_status()
                data = response.json()
                for place in data.get("places", []):
                    seed = seed_from_place(place, query=query)
                    if seed is None:
                        continue
                    key = seed_dedupe_key(seed)
                    if key and key in seen:
                        continue
                    rows.append(seed)
                    if key:
                        seen.add(key)
                    if len(rows) >= target_count:
                        break

                page_token = normalize_text(data.get("nextPageToken"))
                if not page_token:
                    break
                if self.page_delay_seconds:
                    time.sleep(self.page_delay_seconds)

        return GooglePlacesSeedCollection(
            rows=rows[:target_count],
            requests_made=requests_made,
            queries_attempted=queries_attempted,
        )


def build_home_service_painting_queries(
    *,
    seed_market: str = "Toronto/GTA",
    region_code: str | None = "CA",
    cities: Iterable[str] = TORONTO_GTA_SEED_CITIES,
    query_templates: Iterable[str] = PAINTING_SERVICE_QUERIES,
) -> list[GooglePlacesSeedQuery]:
    return build_niche_queries(
        seed_niche="home_service_painting",
        seed_market=seed_market,
        region_code=region_code,
        cities=cities,
        query_templates=query_templates,
    )


def build_niche_queries(
    *,
    seed_niche: str,
    seed_market: str = "Toronto/GTA",
    region_code: str | None = "CA",
    cities: Iterable[str] = TORONTO_GTA_SEED_CITIES,
    query_templates: Iterable[str] | None = None,
    included_type: str | None = None,
) -> list[GooglePlacesSeedQuery]:
    templates = list(query_templates or NICHE_QUERY_TEMPLATES.get(seed_niche, ()))
    if not templates:
        raise ValueError(f"No Google Places query templates configured for niche: {seed_niche}")
    place_type = included_type if included_type is not None else NICHE_INCLUDED_TYPES.get(seed_niche)
    return [
        GooglePlacesSeedQuery(
            text_query=template.format(city=city),
            seed_market=seed_market,
            region_code=region_code,
            included_type=place_type,
            seed_niche=seed_niche,
        )
        for city in cities
        for template in templates
    ]


def seed_from_place(
    place: dict[str, Any],
    *,
    query: GooglePlacesSeedQuery,
) -> BusinessSeedInput | None:
    if place.get("businessStatus") == "CLOSED_PERMANENTLY":
        return None
    display_name = place.get("displayName") or {}
    company_name = normalize_text(display_name.get("text") or place.get("id"))
    if not company_name:
        return None

    phone = normalize_text(place.get("nationalPhoneNumber") or place.get("internationalPhoneNumber"))
    website_url = normalize_url(place.get("websiteUri"))
    maps_url = normalize_url(place.get("googleMapsUri"))
    address = normalize_text(place.get("formattedAddress"))
    types = [normalize_text(item) for item in place.get("types", []) if normalize_text(item)]
    rating = place.get("rating")
    review_count = place.get("userRatingCount")

    niche_label = query.seed_niche.replace("_", " ").strip()
    signals = ["google places result", f"{niche_label} query"]
    if website_url:
        signals.append("public website")
    if phone:
        signals.append("public phone")
    if place.get("businessStatus") == "OPERATIONAL":
        signals.append("operational")
    if query.included_type and query.included_type in types:
        signals.append(f"{query.included_type.replace('_', ' ')} category")
    if rating is not None:
        signals.append(f"rating {rating}")
    if review_count is not None:
        signals.append(f"{review_count} reviews")

    description_parts = [
        f"{niche_label.title()} provider found through Google Places",
        f"for {query.text_query}",
        f"with rating {rating}" if rating is not None else None,
        f"and {review_count} reviews" if review_count is not None else None,
        f"at {address}" if address else None,
    ]
    description = " ".join(part for part in description_parts if part) + "."

    return BusinessSeedInput.model_validate(
        {
            "company_name": company_name,
            "website_url": website_url,
            "phone": phone,
            "geography": address or query.seed_market,
            "address": address,
            "description": description,
            "source": "google_places_seed",
            "source_url": maps_url or website_url,
            "external_id": normalize_text(place.get("id")),
            "query": query.text_query,
            "signals": signals,
            "seed_niche": query.seed_niche,
            "seed_market": query.seed_market,
            "operator_type": "unknown",
            "raw": {
                "google_places": place,
                "collection_query": query.text_query,
                "seed_market": query.seed_market,
                "seed_niche": query.seed_niche,
            },
        }
    )


def seed_dedupe_key(seed: BusinessSeedInput) -> str | None:
    if seed.external_id:
        return f"external:{seed.source}:{seed.external_id}"
    domain = normalize_domain(seed.website_url)
    if domain:
        return f"domain:{domain}"
    phone = normalize_phone(seed.phone)
    if phone:
        return f"phone:{phone}"
    name = normalize_business_name(seed.company_name)
    address = normalize_text(seed.address or seed.geography)
    if name and address:
        return f"name-address:{name}:{address}"
    if name:
        return f"name:{name}"
    return None


def _request_payload(query: GooglePlacesSeedQuery, *, page_token: str | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "textQuery": query.text_query,
        "pageSize": 20,
        "includePureServiceAreaBusinesses": query.include_pure_service_area_businesses,
    }
    if query.region_code:
        payload["regionCode"] = query.region_code
    if query.included_type:
        payload["includedType"] = query.included_type
        payload["strictTypeFiltering"] = query.strict_type_filtering
    if page_token:
        payload["pageToken"] = page_token
    return payload
