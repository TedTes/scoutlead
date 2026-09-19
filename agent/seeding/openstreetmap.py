from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import httpx

from canonical.normalization import normalize_business_name, normalize_domain, normalize_phone
from seeding.schemas import BusinessSeedInput
from shared.utils import normalize_text, normalize_url


DEFAULT_OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
# Toronto proper plus the immediately adjacent urban area. Keeping the box bounded
# avoids expensive, failure-prone name scans across the entire Golden Horseshoe.
TORONTO_GTA_BBOX = (43.55, -79.70, 43.90, -79.10)


@dataclass(frozen=True)
class OpenStreetMapNichePlan:
    seed_niche: str
    query_label: str
    name_pattern: str
    tag_filters: tuple[tuple[str, str], ...]
    required_name_terms: tuple[str, ...]
    excluded_name_terms: tuple[str, ...] = ()
    excluded_tag_terms: tuple[str, ...] = ()


NICHE_PLANS = {
    "home_service_roofing": OpenStreetMapNichePlan(
        seed_niche="home_service_roofing",
        query_label="roofing contractors",
        name_pattern="roofing|roofer",
        tag_filters=(("craft", "roofer"),),
        required_name_terms=("roofing", "roofer"),
        excluded_name_terms=("supply", "supplies", "truss", "waterproof"),
    ),
    "home_service_hvac": OpenStreetMapNichePlan(
        seed_niche="home_service_hvac",
        query_label="HVAC heating and cooling contractors",
        name_pattern="hvac|heating|cooling|air conditioning",
        tag_filters=(("craft", "hvac"),),
        required_name_terms=("hvac", "heating", "cooling", "air conditioning"),
        excluded_name_terms=(
            "association",
            "hospital",
            "plant",
            "supply",
            "supplies",
            "water cooling system",
        ),
        excluded_tag_terms=("doityourself",),
    ),
    "home_service_landscaping": OpenStreetMapNichePlan(
        seed_niche="home_service_landscaping",
        query_label="landscaping and lawn care companies",
        name_pattern="landscap|lawn care|garden service",
        tag_filters=(("craft", "gardener"),),
        required_name_terms=("landscap", "lawn care", "garden service"),
        excluded_name_terms=("architect", "network", "pest", "station", "supply", "supplies"),
    ),
    "home_service_cleaning": OpenStreetMapNichePlan(
        seed_niche="home_service_cleaning",
        query_label="residential and house cleaning companies",
        name_pattern="cleaning|cleaners|maid",
        tag_filters=(("craft", "cleaner"),),
        required_name_terms=(
            "house cleaning",
            "home cleaning",
            "maid",
            "residential cleaning",
            "cleaning service",
        ),
        excluded_name_terms=("dry clean", "laundry", "carpet", "duct"),
        excluded_tag_terms=("dry_cleaning", "laundry", "clothes"),
    ),
}


@dataclass(frozen=True)
class OpenStreetMapSeedCollection:
    rows: list[BusinessSeedInput]
    elements_read: int


class OpenStreetMapSeedCollector:
    def __init__(
        self,
        *,
        endpoint: str = DEFAULT_OVERPASS_ENDPOINT,
        timeout_seconds: float = 90.0,
    ) -> None:
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def collect(
        self,
        plan: OpenStreetMapNichePlan,
        *,
        seed_market: str,
        target_count: int,
        bbox: tuple[float, float, float, float] = TORONTO_GTA_BBOX,
        existing: Iterable[BusinessSeedInput] = (),
    ) -> OpenStreetMapSeedCollection:
        rows = list(existing)
        seen = {seed_dedupe_key(row) for row in rows if seed_dedupe_key(row)}
        response = httpx.post(
            self.endpoint,
            data={"data": build_overpass_query(plan, bbox=bbox)},
            headers={"User-Agent": "ScoutLead seed collector/1.0"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        elements = response.json().get("elements") or []
        for element in elements:
            seed = seed_from_osm_element(element, plan=plan, seed_market=seed_market)
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
        return OpenStreetMapSeedCollection(rows=rows[:target_count], elements_read=len(elements))


def build_overpass_query(
    plan: OpenStreetMapNichePlan,
    *,
    bbox: tuple[float, float, float, float],
) -> str:
    bounds = ",".join(str(value) for value in bbox)
    selectors = [f'nwr["name"~"{plan.name_pattern}",i]({bounds});']
    selectors.extend(f'nwr["{key}"="{value}"]({bounds});' for key, value in plan.tag_filters)
    return "\n".join(
        [
            "[out:json][timeout:60];",
            "(",
            *(f"  {selector}" for selector in selectors),
            ");",
            "out center tags;",
        ]
    )


def seed_from_osm_element(
    element: dict[str, Any],
    *,
    plan: OpenStreetMapNichePlan,
    seed_market: str,
) -> BusinessSeedInput | None:
    tags = element.get("tags") if isinstance(element.get("tags"), dict) else {}
    name = normalize_text(tags.get("name"))
    if not name:
        return None
    lower_name = name.lower()
    if any(term in lower_name for term in plan.excluded_name_terms):
        return None
    tag_values = " ".join(normalize_text(value).lower() for value in tags.values())
    if any(term in tag_values for term in plan.excluded_tag_terms):
        return None
    has_service_tag = any(
        normalize_text(tags.get(key)).lower() == value.lower() for key, value in plan.tag_filters
    )
    has_service_name = any(term in lower_name for term in plan.required_name_terms)
    if not has_service_tag and not has_service_name:
        return None

    element_type = normalize_text(element.get("type"))
    element_id = element.get("id")
    if not element_type or element_id is None:
        return None
    source_url = f"https://www.openstreetmap.org/{element_type}/{element_id}"
    website = normalize_url(tags.get("contact:website") or tags.get("website") or tags.get("url"))
    phone = normalize_text(tags.get("contact:phone") or tags.get("phone"))
    email = normalize_text(tags.get("contact:email") or tags.get("email"))
    address = _address(tags)
    latitude, longitude = _coordinates(element)
    matched_tags = [
        f"{key}={value}"
        for key, value in plan.tag_filters
        if normalize_text(tags.get(key)).lower() == value.lower()
    ]
    signals = ["OpenStreetMap business listing", *matched_tags]
    if website:
        signals.append("public website")
    if phone:
        signals.append("public phone")
    if email:
        signals.append("public email")

    return BusinessSeedInput.model_validate(
        {
            "company_name": name,
            "website_url": website,
            "phone": phone,
            "contact_email": email,
            "geography": address or seed_market,
            "address": address,
            "description": f"{plan.query_label.title()} listing found in OpenStreetMap.",
            "source": "openstreetmap_seed",
            "source_url": source_url,
            "external_id": f"osm:{element_type}:{element_id}",
            "query": f"{plan.query_label} in {seed_market}",
            "signals": signals,
            "seed_niche": plan.seed_niche,
            "seed_market": seed_market,
            "operator_type": "unknown",
            "raw": {
                "openstreetmap": {
                    "element_type": element_type,
                    "element_id": element_id,
                    "latitude": latitude,
                    "longitude": longitude,
                    "tags": tags,
                },
                "attribution": "OpenStreetMap contributors",
                "license": "ODbL",
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
    return f"name:{name}" if name else None


def _address(tags: dict[str, Any]) -> str | None:
    street = " ".join(
        part
        for part in (
            normalize_text(tags.get("addr:housenumber")),
            normalize_text(tags.get("addr:street")),
        )
        if part
    )
    parts = [
        street,
        normalize_text(tags.get("addr:city")),
        normalize_text(tags.get("addr:province") or tags.get("addr:state")),
        normalize_text(tags.get("addr:postcode")),
    ]
    address = ", ".join(part for part in parts if part)
    return address or None


def _coordinates(element: dict[str, Any]) -> tuple[float | None, float | None]:
    center = element.get("center") if isinstance(element.get("center"), dict) else {}
    latitude = element.get("lat", center.get("lat"))
    longitude = element.get("lon", center.get("lon"))
    return latitude, longitude
