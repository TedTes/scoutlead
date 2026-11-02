from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from canonical.normalization import nested_raw


GOOGLE_NON_BUSINESS_TYPES = frozenset(
    {
        "administrative_area_level_1",
        "administrative_area_level_2",
        "administrative_area_level_3",
        "bus_station",
        "country",
        "intersection",
        "light_rail_station",
        "locality",
        "neighborhood",
        "plus_code",
        "postal_code",
        "premise",
        "route",
        "street_address",
        "subpremise",
        "subway_station",
        "train_station",
        "transit_station",
    }
)
GOOGLE_GENERIC_TYPES = frozenset({"establishment", "point_of_interest"})
OSM_NON_BUSINESS_HIGHWAYS = frozenset(
    {"bus_stop", "crossing", "motorway_junction", "platform", "traffic_signals"}
)
OSM_NON_BUSINESS_PUBLIC_TRANSPORT = frozenset(
    {"platform", "station", "stop_area", "stop_position"}
)


@dataclass(frozen=True)
class BusinessEntityAssessment:
    is_business: bool | None
    reason: str
    evidence: dict[str, Any]


def assess_provider_business_entity(
    *,
    source: str,
    payload: dict[str, Any],
) -> BusinessEntityAssessment:
    raw = nested_raw(payload)
    provider = str(source or raw.get("provider_id") or raw.get("source") or "").lower()
    if provider in {"google_places", "google_places_seed"}:
        primary_type = str(
            raw.get("primaryType") or raw.get("primaryTypeDisplayName") or ""
        ).strip()
        primary_type_key = primary_type.lower().replace(" ", "_")
        types = {
            str(value).strip().lower()
            for value in (raw.get("types") or [])
            if str(value).strip()
        }
        blocked = sorted(
            (types & GOOGLE_NON_BUSINESS_TYPES)
            | ({primary_type_key} if primary_type_key in GOOGLE_NON_BUSINESS_TYPES else set())
        )
        if blocked:
            return BusinessEntityAssessment(
                False,
                "Google Places identifies this result as a non-business map entity.",
                {"provider": provider, "types": sorted(types), "blocked_types": blocked},
            )
        if primary_type:
            return BusinessEntityAssessment(
                True,
                "Google Places includes a primary business or service type.",
                {
                    "provider": provider,
                    "types": sorted(types),
                    "primary_type": primary_type,
                },
            )
        business_types = sorted(types - GOOGLE_GENERIC_TYPES)
        if business_types:
            return BusinessEntityAssessment(
                True,
                "Google Places includes a business or service Place type.",
                {"provider": provider, "types": sorted(types), "business_types": business_types},
            )
        if types and types <= GOOGLE_GENERIC_TYPES:
            has_business_fields = bool(
                raw.get("nationalPhoneNumber")
                or raw.get("internationalPhoneNumber")
                or raw.get("websiteUri")
                or raw.get("website_url")
            )
            return BusinessEntityAssessment(
                True if has_business_fields else None,
                (
                    "A generic Google Place has business contact fields."
                    if has_business_fields
                    else "Google Places returned only generic Place types without business fields."
                ),
                {"provider": provider, "types": sorted(types)},
            )
        legacy_business_fields = bool(
            raw.get("businessStatus")
            and (raw.get("id") or raw.get("displayName") or raw.get("nationalPhoneNumber"))
        )
        return BusinessEntityAssessment(
            True if legacy_business_fields else None,
            (
                "Google Places returned business-status fields, but no Place types."
                if legacy_business_fields
                else "Google Places did not return Place types for business verification."
            ),
            {"provider": provider, "types": [], "legacy_business_fields": legacy_business_fields},
        )

    if provider in {"openstreetmap", "openstreetmap_seed"}:
        tags = raw.get("tags") if isinstance(raw.get("tags"), dict) else {}
        highway = str(tags.get("highway") or "").strip().lower()
        public_transport = str(tags.get("public_transport") or "").strip().lower()
        railway = str(tags.get("railway") or "").strip().lower()
        blockers = []
        if highway in OSM_NON_BUSINESS_HIGHWAYS:
            blockers.append(f"highway={highway}")
        if public_transport in OSM_NON_BUSINESS_PUBLIC_TRANSPORT:
            blockers.append(f"public_transport={public_transport}")
        if railway in {"halt", "platform", "station", "stop"}:
            blockers.append(f"railway={railway}")
        if blockers:
            return BusinessEntityAssessment(
                False,
                "OpenStreetMap identifies this result as transport infrastructure, not a business.",
                {"provider": provider, "blocked_tags": blockers, "tags": tags},
            )
        business_tags = {
            key: tags.get(key)
            for key in ("craft", "office", "shop")
            if tags.get(key)
        }
        return BusinessEntityAssessment(
            True if business_tags else None,
            (
                "OpenStreetMap includes structured business tags."
                if business_tags
                else "OpenStreetMap does not include structured business tags."
            ),
            {"provider": provider, "business_tags": business_tags},
        )

    return BusinessEntityAssessment(
        None,
        "This provider does not expose a structured business entity type.",
        {"provider": provider},
    )


def google_place_is_business_profile(place: dict[str, Any]) -> bool:
    assessment = assess_provider_business_entity(source="google_places", payload=place)
    return assessment.is_business is True


def osm_element_is_non_business(tags: dict[str, Any]) -> bool:
    assessment = assess_provider_business_entity(
        source="openstreetmap",
        payload={"tags": tags},
    )
    return assessment.is_business is False
