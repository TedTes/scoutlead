from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from math import asin, cos, radians, sin, sqrt
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
    "home_service_plumbing": [
        "plumbers {city}",
        "plumbing contractors {city}",
        "residential plumbing services {city}",
    ],
    "home_service_electrical": [
        "electricians {city}",
        "electrical contractors {city}",
        "residential electrical services {city}",
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
    # Google Places has no HVAC filter type. Keep HVAC precision in the query
    # text and enforce geography/identity after the response.
    "home_service_hvac": None,
    "home_service_plumbing": "plumber",
    "home_service_electrical": "electrician",
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

KNOWN_FRANCHISES = (
    "benjamin franklin plumbing",
    "certapro painters",
    "five star painting",
    "mr electric",
    "mr rooter",
    "one hour heating and air conditioning",
    "roto rooter",
    "wow 1 day painting",
)

KNOWN_CHAINS = (
    "aire one",
    "enercare",
    "reliance home comfort",
    "reliance heating",
)

HVAC_NAME_MARKERS = (
    "air",
    "air conditioning",
    "airflow",
    "climate",
    "cooling",
    "furnace",
    "heating",
    "home comfort",
    "hvac",
    "mechanical",
)


@dataclass(frozen=True)
class GooglePlacesSeedQuery:
    text_query: str
    seed_market: str
    region_code: str | None = "CA"
    included_type: str | None = "painter"
    strict_type_filtering: bool = False
    include_pure_service_area_businesses: bool = True
    seed_niche: str = "home_service_painting"
    city: str | None = None
    center_latitude: float | None = None
    center_longitude: float | None = None
    radius_meters: float | None = None
    customer_kind: str = "residential"
    require_phone: bool = False
    expected_name: str | None = None


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
        max_results_per_query: int | None = None,
    ) -> GooglePlacesSeedCollection:
        rows = list(existing)
        seen = {
            key
            for row in rows
            for key in seed_identity_keys(row)
        }
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
            query_result_count = 0

            while len(rows) < target_count and pages_loaded < max_pages_per_query:
                if (
                    max_results_per_query is not None
                    and query_result_count >= max_results_per_query
                ):
                    break
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
                    keys = seed_identity_keys(seed)
                    if keys & seen:
                        continue
                    rows.append(seed)
                    query_result_count += 1
                    seen.update(keys)
                    if len(rows) >= target_count:
                        break
                    if (
                        max_results_per_query is not None
                        and query_result_count >= max_results_per_query
                    ):
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
    city: str | None = None,
    center_latitude: float | None = None,
    center_longitude: float | None = None,
    radius_meters: float | None = None,
    require_phone: bool = False,
) -> list[GooglePlacesSeedQuery]:
    return build_niche_queries(
        seed_niche="home_service_painting",
        seed_market=seed_market,
        region_code=region_code,
        cities=cities,
        query_templates=query_templates,
        city=city,
        center_latitude=center_latitude,
        center_longitude=center_longitude,
        radius_meters=radius_meters,
        require_phone=require_phone,
    )


def build_niche_queries(
    *,
    seed_niche: str,
    seed_market: str = "Toronto/GTA",
    region_code: str | None = "CA",
    cities: Iterable[str] = TORONTO_GTA_SEED_CITIES,
    query_templates: Iterable[str] | None = None,
    included_type: str | None = None,
    city: str | None = None,
    center_latitude: float | None = None,
    center_longitude: float | None = None,
    radius_meters: float | None = None,
    customer_kind: str = "residential",
    require_phone: bool = False,
) -> list[GooglePlacesSeedQuery]:
    templates = list(query_templates or NICHE_QUERY_TEMPLATES.get(seed_niche, ()))
    if not templates:
        raise ValueError(f"No Google Places query templates configured for niche: {seed_niche}")
    place_type = included_type if included_type is not None else NICHE_INCLUDED_TYPES.get(seed_niche)
    return [
        GooglePlacesSeedQuery(
            text_query=template.format(city=search_city),
            seed_market=seed_market,
            region_code=region_code,
            included_type=place_type,
            seed_niche=seed_niche,
            city=city or search_city,
            center_latitude=center_latitude,
            center_longitude=center_longitude,
            radius_meters=radius_meters,
            customer_kind=customer_kind,
            require_phone=require_phone,
        )
        for search_city in cities
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
    if query.expected_name and not _business_name_matches(query.expected_name, company_name):
        return None

    phone = normalize_text(place.get("nationalPhoneNumber") or place.get("internationalPhoneNumber"))
    if query.require_phone and not phone:
        return None
    website_url = normalize_url(place.get("websiteUri"))
    maps_url = normalize_url(place.get("googleMapsUri"))
    address = normalize_text(place.get("formattedAddress"))
    types = [normalize_text(item) for item in place.get("types", []) if normalize_text(item)]
    if not _matches_niche(company_name, types=types, niche=query.seed_niche):
        return None
    rating = place.get("rating")
    review_count = place.get("userRatingCount")
    location = place.get("location") if isinstance(place.get("location"), dict) else {}
    latitude = _coordinate(location.get("latitude"), minimum=-90, maximum=90)
    longitude = _coordinate(location.get("longitude"), minimum=-180, maximum=180)
    if query.center_latitude is not None and query.center_longitude is not None:
        if latitude is None or longitude is None:
            return None
        if query.radius_meters is not None and _distance_meters(
            query.center_latitude,
            query.center_longitude,
            latitude,
            longitude,
        ) > query.radius_meters:
            return None
    is_franchise = _known_brand(company_name, KNOWN_FRANCHISES)
    is_chain = is_franchise or _known_brand(company_name, KNOWN_CHAINS)

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
            "city": query.city,
            "latitude": latitude,
            "longitude": longitude,
            "customer_kind": query.customer_kind,
            "is_chain": True if is_chain else None,
            "is_franchise": True if is_franchise else None,
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
                "city": query.city,
                "latitude": latitude,
                "longitude": longitude,
                "customer_kind": query.customer_kind,
                "is_chain": True if is_chain else None,
                "is_franchise": True if is_franchise else None,
                "website_presence": {
                    "status": "active" if website_url else "no_website_listed",
                    "website_url": website_url,
                },
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


def seed_identity_keys(seed: BusinessSeedInput) -> set[str]:
    keys: set[str] = set()
    if seed.external_id:
        keys.add(f"external:{seed.source}:{seed.external_id}")
    domain = normalize_domain(seed.website_url)
    if domain:
        keys.add(f"domain:{domain}")
    phone = normalize_phone(seed.phone)
    if phone:
        keys.add(f"phone:{phone}")
    name = normalize_business_name(seed.company_name)
    address = normalize_text(seed.address or seed.geography)
    if name and address:
        keys.add(f"name-address:{name}:{address}")
    elif name:
        keys.add(f"name:{name}")
    return keys


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
    if query.center_latitude is not None and query.center_longitude is not None:
        payload["locationBias"] = {
            "circle": {
                "center": {
                    "latitude": query.center_latitude,
                    "longitude": query.center_longitude,
                },
                "radius": query.radius_meters or 25_000,
            }
        }
    if page_token:
        payload["pageToken"] = page_token
    return payload


def _known_brand(company_name: str, markers: tuple[str, ...]) -> bool:
    normalized = normalize_business_name(company_name)
    return any(marker in normalized for marker in markers)


def _matches_niche(company_name: str, *, types: list[str], niche: str) -> bool:
    if niche != "home_service_hvac":
        return True
    normalized_name = normalize_business_name(company_name)
    name_tokens = set(normalized_name.split())
    return any(
        marker in name_tokens if marker == "air" else marker in normalized_name
        for marker in HVAC_NAME_MARKERS
    )


def _business_name_matches(expected: str, actual: str) -> bool:
    expected_name = normalize_business_name(expected)
    actual_name = normalize_business_name(actual)
    if not expected_name or not actual_name:
        return False
    if expected_name in actual_name:
        return True
    expected_tokens = set(expected_name.split())
    actual_tokens = set(actual_name.split())
    token_overlap = len(expected_tokens & actual_tokens) / max(1, len(expected_tokens))
    return token_overlap >= 0.8 and SequenceMatcher(None, expected_name, actual_name).ratio() >= 0.7


def _coordinate(value: Any, *, minimum: float, maximum: float) -> float | None:
    try:
        coordinate = float(value)
    except (TypeError, ValueError):
        return None
    return coordinate if minimum <= coordinate <= maximum else None


def _distance_meters(
    first_latitude: float,
    first_longitude: float,
    second_latitude: float,
    second_longitude: float,
) -> float:
    lat_delta = radians(second_latitude - first_latitude)
    lng_delta = radians(second_longitude - first_longitude)
    first_lat = radians(first_latitude)
    second_lat = radians(second_latitude)
    value = (
        sin(lat_delta / 2) ** 2
        + cos(first_lat) * cos(second_lat) * sin(lng_delta / 2) ** 2
    )
    return 2 * 6_371_000 * asin(sqrt(value))
