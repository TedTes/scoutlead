from __future__ import annotations

import re
from typing import Any

import httpx

from campaign_sources.schemas import CampaignSourceRead
from campaigns.schemas import CampaignRead
from canonical.normalization import normalize_business_name, normalize_phone
from shared.errors import ConfigurationError
from shared.utils import normalize_text, normalize_url
from tools.base import ToolResult, ToolSlot, measured_tool_result
from tools.search import SearchResult


DEFAULT_OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
DEFAULT_NOMINATIM_ENDPOINT = "https://nominatim.openstreetmap.org/search"

_CATEGORY_TAGS: tuple[tuple[tuple[str, ...], tuple[str, str], str], ...] = (
    (("paint", "painter"), ("craft", "painter"), "paint|painter|painting"),
    (("roof", "roofer"), ("craft", "roofer"), "roof|roofer|roofing"),
    (("plumb", "plumber"), ("craft", "plumber"), "plumb|plumber|plumbing"),
    (("hvac", "heating", "cooling"), ("craft", "hvac"), "hvac|heating|cooling"),
    (("electric", "electrician"), ("craft", "electrician"), "electric|electrician"),
    (("landscap", "lawn", "gardener"), ("craft", "gardener"), "landscap|lawn|gardener"),
    (("clean", "maid"), ("craft", "cleaner"), "cleaning|cleaner|maid"),
)


class OpenStreetMapDiscoveryAdapter:
    provider_id = "openstreetmap"

    def __init__(
        self,
        *,
        overpass_endpoint: str | None = None,
        nominatim_endpoint: str | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.overpass_endpoint = overpass_endpoint or DEFAULT_OVERPASS_ENDPOINT
        self.nominatim_endpoint = nominatim_endpoint or DEFAULT_NOMINATIM_ENDPOINT
        self.timeout_seconds = timeout_seconds

    @property
    def is_configured(self) -> bool:
        return True

    def run(self, source: CampaignSourceRead, context: dict[str, Any]) -> ToolResult:
        campaign = CampaignRead.model_validate(context["campaign"])
        category = normalize_text(
            source.input.get("business_category") or source.input.get("query")
        )
        location = normalize_text(
            source.input.get("location") or source.input.get("geography")
        )
        if not category or not location:
            raise ConfigurationError(
                "OpenStreetMap discovery requires a business category and location",
                {"campaign_source_id": source.id},
            )
        limit = int(source.config.get("limit") or campaign.max_leads)
        website_policy = str(
            source.config.get("website_policy")
            or source.input.get("website_policy")
            or "any"
        )

        def action() -> list[dict[str, Any]]:
            bbox = self._resolve_bbox(location, source.config.get("bbox"))
            query = build_overpass_query(category, bbox=bbox)
            response = httpx.post(
                self.overpass_endpoint,
                data={"data": query},
                headers={"User-Agent": "ScoutLead discovery/1.0"},
                timeout=max(self.timeout_seconds, 60.0),
            )
            response.raise_for_status()
            rows: list[SearchResult] = []
            seen: set[str] = set()
            for element in response.json().get("elements") or []:
                result = result_from_osm_element(
                    element,
                    category=category,
                    location=location,
                )
                if result is None or not _matches_website_policy(result, website_policy):
                    continue
                keys = _result_keys(result)
                if keys & seen:
                    continue
                seen.update(keys)
                rows.append(result)
                if len(rows) >= limit:
                    break
            return [row.model_dump(mode="json") for row in rows]

        return measured_tool_result(
            provider=self.provider_id,
            slot=ToolSlot.DISCOVERY,
            confidence=75,
            raw={
                "campaign_source_id": source.id,
                "provider_id": self.provider_id,
                "category": category,
                "location": location,
                "website_policy": website_policy,
            },
            action=action,
        )

    def _resolve_bbox(self, location: str, configured: Any) -> tuple[float, float, float, float]:
        if isinstance(configured, list) and len(configured) == 4:
            return tuple(float(value) for value in configured)  # type: ignore[return-value]
        response = httpx.get(
            self.nominatim_endpoint,
            params={"q": location, "format": "jsonv2", "limit": 1},
            headers={"User-Agent": "ScoutLead discovery/1.0"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list) or not rows:
            raise ConfigurationError(
                "OpenStreetMap location could not be resolved",
                {"location": location},
            )
        bounds = rows[0].get("boundingbox")
        if not isinstance(bounds, list) or len(bounds) != 4:
            raise ConfigurationError(
                "OpenStreetMap location did not include usable bounds",
                {"location": location},
            )
        south, north, west, east = (float(value) for value in bounds)
        return south, west, north, east


def build_overpass_query(
    category: str,
    *,
    bbox: tuple[float, float, float, float],
) -> str:
    bounds = ",".join(str(value) for value in bbox)
    tag, pattern = _category_rule(category)
    selectors = [f'nwr["name"~"{pattern}",i]({bounds});']
    if tag is not None:
        selectors.append(f'nwr["{tag[0]}"="{tag[1]}"]({bounds});')
    return "\n".join(
        [
            "[out:json][timeout:60];",
            "(",
            *(f"  {selector}" for selector in selectors),
            ");",
            "out center tags;",
        ]
    )


def result_from_osm_element(
    element: dict[str, Any],
    *,
    category: str,
    location: str,
) -> SearchResult | None:
    tags = element.get("tags") if isinstance(element.get("tags"), dict) else {}
    name = normalize_text(tags.get("name"))
    element_type = normalize_text(element.get("type"))
    element_id = element.get("id")
    if not name or not element_type or element_id is None:
        return None
    tag, pattern = _category_rule(category)
    tag_match = bool(tag and normalize_text(tags.get(tag[0])).lower() == tag[1])
    if not tag_match and re.search(pattern, name, flags=re.IGNORECASE) is None:
        return None
    website = normalize_url(tags.get("contact:website") or tags.get("website") or tags.get("url"))
    phone = normalize_text(tags.get("contact:phone") or tags.get("phone"))
    email = normalize_text(tags.get("contact:email") or tags.get("email"))
    address = _address(tags) or location
    source_url = f"https://www.openstreetmap.org/{element_type}/{element_id}"
    return SearchResult(
        title=name,
        url=website,
        snippet=" | ".join(
            part for part in (address, f"phone: {phone}" if phone else None) if part
        ),
        geography=address,
        contact_email=email or None,
        source="openstreetmap",
        raw={
            "external_id": f"osm:{element_type}:{element_id}",
            "source_url": source_url,
            "phone": phone or None,
            "address": address,
            "businessStatus": "OPERATIONAL",
            "website_url": website,
            "query": f"{category} in {location}",
            "tags": tags,
            "attribution": "OpenStreetMap contributors",
            "license": "ODbL",
            **(
                {
                    "website_presence_status": "no_website_listed",
                    "website_presence_label": "No website listed",
                }
                if not website
                else {}
            ),
        },
    )


def _category_rule(category: str) -> tuple[tuple[str, str] | None, str]:
    normalized = category.lower()
    for terms, tag, pattern in _CATEGORY_TAGS:
        if any(term in normalized for term in terms):
            return tag, pattern
    words = [
        re.escape(word)
        for word in re.findall(r"[a-z0-9]+", normalized)
        if len(word) >= 4 and word not in {"business", "service", "services", "company"}
    ]
    return None, "|".join(words[:5]) or re.escape(normalized)


def _matches_website_policy(result: SearchResult, website_policy: str) -> bool:
    if website_policy == "missing":
        return not result.url
    return True


def _result_keys(result: SearchResult) -> set[str]:
    raw = result.raw or {}
    name = normalize_business_name(result.title)
    phone = normalize_phone(raw.get("phone"))
    address = normalize_text(raw.get("address")).lower()
    keys = {f"external:{raw['external_id']}"} if raw.get("external_id") else set()
    if name and phone:
        keys.add(f"name-phone:{name}|{phone}")
    if name and address:
        keys.add(f"name-address:{name}|{address}")
    return keys or {f"name:{name}"}


def _address(tags: dict[str, Any]) -> str | None:
    street = " ".join(
        part
        for part in (
            normalize_text(tags.get("addr:housenumber")),
            normalize_text(tags.get("addr:street")),
        )
        if part
    )
    address = ", ".join(
        part
        for part in (
            street,
            normalize_text(tags.get("addr:city")),
            normalize_text(tags.get("addr:province") or tags.get("addr:state")),
            normalize_text(tags.get("addr:postcode")),
        )
        if part
    )
    return address or None
