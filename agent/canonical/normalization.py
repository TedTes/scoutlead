from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from urllib.parse import urlparse

from shared.utils import normalize_text, normalize_url


_LEGAL_SUFFIXES = {
    "co",
    "company",
    "corp",
    "corporation",
    "inc",
    "incorporated",
    "limited",
    "llc",
    "ltd",
}

_EXTERNAL_ID_KEYS = (
    "external_id",
    "id",
    "place_id",
    "placeId",
    "listing_id",
    "listingId",
    "ad_id",
    "adId",
)

_CONTACT_NAME_KEYS = (
    "normalized_contact_name",
    "contact_name",
    "contactName",
    "sellerName",
    "ownerName",
    "name",
)

_EMAIL_KEYS = (
    "contact_email",
    "contactEmail",
    "sellerEmail",
    "ownerEmail",
    "email",
)

_PHONE_KEYS = (
    "normalized_contact_phone",
    "contact_phone",
    "contactPhone",
    "sellerPhone",
    "ownerPhone",
    "nationalPhoneNumber",
    "internationalPhoneNumber",
    "phone",
    "phoneNumber",
    "phone_number",
    "telephone",
)

_SOURCE_URL_KEYS = (
    "url",
    "website_url",
    "websiteUri",
    "google_maps_url",
    "googleMapsUri",
    "listingUrl",
    "adUrl",
)


def normalize_business_name(value: str) -> str:
    normalized = normalize_text(value).lower()
    normalized = normalized.replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    tokens = [token for token in normalized.split() if token]
    while tokens and tokens[-1] in _LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def normalize_domain(value: str | None) -> str | None:
    url = normalize_url(value)
    if not url:
        return None
    parsed = urlparse(url)
    host = parsed.netloc.lower().split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host or None


def normalize_email(value: str | None) -> str | None:
    normalized = normalize_text(value).lower()
    return normalized or None


def normalize_phone(value: str | int | float | None) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    leading_plus = raw.startswith("+")
    digits = re.sub(r"\D+", "", raw)
    if len(digits) < 7:
        return None
    return f"+{digits}" if leading_plus else digits


def query_signature(*, source: str, query: str | None) -> str | None:
    normalized_query = normalize_text(query).lower()
    normalized_source = normalize_text(source).lower()
    if not normalized_query:
        return None
    return f"{normalized_source}:{normalized_query}"


def query_from_source_input(source_input: dict[str, Any]) -> str | None:
    query = normalize_text(str(source_input.get("query") or source_input.get("value") or ""))
    geography = normalize_text(str(source_input.get("geography") or ""))
    if geography and geography.lower() not in query.lower():
        query = f"{query} {geography}".strip()
    return query or None


def source_input_signature(*, source: str, source_input: dict[str, Any]) -> str | None:
    return query_signature(source=source, query=query_from_source_input(source_input))


def stable_content_hash(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def iter_raw_layers(raw: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    layers = [raw]
    nested = raw.get("raw")
    while isinstance(nested, dict):
        layers.append(nested)
        nested = nested.get("raw")
    return layers


def nested_raw(raw: dict[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for layer in reversed(iter_raw_layers(raw)):
        merged.update(layer)
    return merged


def first_raw_text(raw: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for layer in iter_raw_layers(raw):
        for key in keys:
            value = layer.get(key)
            if isinstance(value, str) and value.strip():
                return normalize_text(value)
            if isinstance(value, (int, float)):
                return str(value)
    return None


def external_id_from_raw(raw: dict[str, Any] | None) -> str | None:
    return first_raw_text(nested_raw(raw), _EXTERNAL_ID_KEYS)


def contact_name_from_raw(raw: dict[str, Any] | None) -> str | None:
    return first_raw_text(nested_raw(raw), _CONTACT_NAME_KEYS)


def email_from_raw(raw: dict[str, Any] | None) -> str | None:
    return normalize_email(first_raw_text(nested_raw(raw), _EMAIL_KEYS))


def phone_from_raw(raw: dict[str, Any] | None) -> str | None:
    return normalize_phone(first_raw_text(nested_raw(raw), _PHONE_KEYS))


def source_url_from_raw(raw: dict[str, Any] | None) -> str | None:
    return normalize_url(first_raw_text(nested_raw(raw), _SOURCE_URL_KEYS))
