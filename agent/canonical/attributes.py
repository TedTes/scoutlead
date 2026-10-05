from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Iterator


@dataclass(frozen=True)
class BusinessAttributes:
    latitude: float | None = None
    longitude: float | None = None
    customer_kind: str | None = None
    is_chain: bool | None = None
    is_franchise: bool | None = None
    is_directory: bool | None = None
    is_agency: bool | None = None
    operational: bool | None = None


def extract_business_attributes(
    payloads: Iterable[dict[str, Any]],
    *,
    category: str | None = None,
) -> BusinessAttributes:
    values = [payload for payload in payloads if isinstance(payload, dict)]
    latitude, longitude = _coordinates(values)
    customer_kind = _customer_kind(values)
    is_chain = _explicit_bool(values, {"is_chain", "isChain", "chain"})
    is_franchise = _explicit_bool(
        values,
        {"is_franchise", "isFranchise", "franchise"},
    )
    is_directory = _explicit_bool(
        values,
        {"is_directory", "isDirectory", "directory"},
    )
    is_agency = _explicit_bool(values, {"is_agency", "isAgency", "agency"})
    operational = _operational(values)

    candidate_types = {
        str(value).strip().lower()
        for value in _values(values, {"candidate_type", "candidateType"})
        if value is not None
    }
    if is_directory is None and "directory" in candidate_types:
        is_directory = True
    if is_directory is None and "target_business" in candidate_types:
        is_directory = False

    type_values = {
        str(value).strip().lower().replace(" ", "_")
        for value in _flattened_values(values, {"types", "categories", "category"})
        if value is not None
    }
    normalized_category = str(category or "").strip().lower().replace(" ", "_")
    if normalized_category:
        type_values.add(normalized_category)
    agency_types = {
        "advertising_agency",
        "digital_marketing_agency",
        "marketing_agency",
        "seo_agency",
        "web_design",
        "web_design_agency",
    }
    if is_agency is None and type_values.intersection(agency_types):
        is_agency = True

    return BusinessAttributes(
        latitude=latitude,
        longitude=longitude,
        customer_kind=customer_kind,
        is_chain=is_chain,
        is_franchise=is_franchise,
        is_directory=is_directory,
        is_agency=is_agency,
        operational=operational,
    )


def apply_business_attributes(business, attributes: BusinessAttributes) -> None:
    for field in (
        "latitude",
        "longitude",
        "is_chain",
        "is_franchise",
        "is_directory",
        "is_agency",
    ):
        value = getattr(attributes, field)
        if value is not None:
            setattr(business, field, value)
    if attributes.customer_kind in {"residential", "commercial"}:
        business.customer_kind = attributes.customer_kind
    elif not getattr(business, "customer_kind", None):
        business.customer_kind = "unknown"
    if attributes.operational is False:
        business.status = "closed"
    elif attributes.operational is True and business.status == "closed":
        business.status = "active"


def _coordinates(payloads: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    for node in _dict_nodes(payloads):
        latitude = _number(node.get("latitude", node.get("lat")))
        longitude = _number(
            node.get("longitude", node.get("lng", node.get("lon")))
        )
        if (
            latitude is not None
            and longitude is not None
            and -90 <= latitude <= 90
            and -180 <= longitude <= 180
        ):
            return latitude, longitude
    return None, None


def _customer_kind(payloads: list[dict[str, Any]]) -> str | None:
    for value in _values(
        payloads,
        {"customer_kind", "customerKind", "customer_type", "customerType"},
    ):
        normalized = str(value or "").strip().lower()
        if normalized in {"residential", "commercial"}:
            return normalized
    return None


def _operational(payloads: list[dict[str, Any]]) -> bool | None:
    for value in _values(payloads, {"businessStatus", "business_status"}):
        normalized = str(value or "").strip().upper()
        if normalized == "OPERATIONAL":
            return True
        if normalized in {"CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY", "CLOSED"}:
            return False
    return None


def _explicit_bool(payloads: list[dict[str, Any]], keys: set[str]) -> bool | None:
    for value in _values(payloads, keys):
        if isinstance(value, bool):
            return value
        normalized = str(value or "").strip().lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
    return None


def _values(payloads: list[dict[str, Any]], keys: set[str]) -> Iterator[Any]:
    for node in _dict_nodes(payloads):
        for key in keys:
            if key in node:
                yield node[key]


def _flattened_values(
    payloads: list[dict[str, Any]],
    keys: set[str],
) -> Iterator[Any]:
    for value in _values(payloads, keys):
        if isinstance(value, list):
            yield from value
        else:
            yield value


def _dict_nodes(values: Iterable[Any]) -> Iterator[dict[str, Any]]:
    stack = list(values)
    while stack:
        value = stack.pop(0)
        if isinstance(value, dict):
            yield value
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
