from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from canonical.normalization import (
    first_raw_text,
    iter_raw_layers,
    nested_raw,
    query_from_source_input,
)
from shared.utils import normalize_text, safe_json_loads


@dataclass(frozen=True)
class SemanticProfile:
    category_key: str | None
    market_key: str | None
    text: str


def business_semantic_profile(
    *,
    company_name: str,
    website_url: str | None,
    geography: str | None,
    description: str | None,
    source: str,
    raw: dict[str, Any],
) -> SemanticProfile:
    intent = source_request_intent_from_raw(raw)
    category = _intent_text(intent, "business_category") or _raw_text(
        raw,
        (
            "business_category",
            "businessCategory",
            "category",
            "primaryTypeDisplayName",
            "type",
        ),
    )
    market = _market_from_intent(intent) or _raw_text(
        raw,
        (
            "geography",
            "discovery_geography",
            "formattedAddress",
            "address",
            "location",
        ),
    )
    query = _query_from_raw(raw)
    signals = _intent_list(intent, "required_signals")
    type_text = _list_text(raw, ("types", "categories"))
    parts = [
        f"Business: {company_name}",
        f"Category: {category}" if category else None,
        f"Market: {market or geography}" if market or geography else None,
        f"Description: {description}" if description else None,
        f"Source query: {query}" if query else None,
        f"Signals: {', '.join(signals)}" if signals else None,
        f"Source types: {type_text}" if type_text else None,
        f"Website: {website_url}" if website_url else None,
        f"Source: {source}" if source else None,
    ]
    return SemanticProfile(
        category_key=semantic_key(category or query),
        market_key=semantic_key(market or geography),
        text=_join_parts(parts),
    )


def request_semantic_profile(
    *,
    source_inputs: dict[str, Any],
    source_input: str | None,
) -> SemanticProfile:
    intent = source_request_intent_from_mapping(source_inputs)
    category = (
        _intent_text(intent, "business_category")
        or _mapping_text(source_inputs, "business_category")
        or _mapping_text(source_inputs, "category")
    )
    market = (
        _market_from_intent(intent)
        or _mapping_text(source_inputs, "geography")
        or _mapping_text(source_inputs, "location")
    )
    query = normalize_text(source_input) or normalize_text(
        str(source_inputs.get("compiled_query") or "")
    )
    prompt = _mapping_text(source_inputs, "source_request_prompt")
    signals = _intent_list(intent, "required_signals")
    parts = [
        f"Business category: {category}" if category else None,
        f"Market: {market}" if market else None,
        f"Search query: {query}" if query else None,
        f"User request: {prompt}" if prompt else None,
        f"Required signals: {', '.join(signals)}" if signals else None,
    ]
    return SemanticProfile(
        category_key=semantic_key(category or query),
        market_key=semantic_key(market),
        text=_join_parts(parts),
    )


def source_request_intent_from_raw(raw: dict[str, Any]) -> dict[str, Any] | None:
    for layer in iter_raw_layers(raw):
        intent = source_request_intent_from_mapping(layer)
        if intent:
            return intent
        source_input = layer.get("source_input")
        if isinstance(source_input, dict):
            intent = source_request_intent_from_mapping(source_input)
            if intent:
                return intent
    return None


def source_request_intent_from_mapping(mapping: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(mapping, dict):
        return None
    value = mapping.get("source_request_intent")
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        parsed = safe_json_loads(value)
        if isinstance(parsed, dict):
            return parsed
    return None


def semantic_key(value: str | None) -> str | None:
    normalized = normalize_text(value).lower()
    if not normalized:
        return None
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = " ".join(normalized.split())
    return normalized or None


def cosine_similarity(left: list[float] | None, right: list[float] | None) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = sum(a * a for a in left) ** 0.5
    right_norm = sum(b * b for b in right) ** 0.5
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def market_is_compatible(request_market_key: str | None, business_market_key: str | None) -> bool:
    if not request_market_key or not business_market_key:
        return True
    if request_market_key == business_market_key:
        return True
    request_tokens = _meaningful_tokens(request_market_key)
    business_tokens = _meaningful_tokens(business_market_key)
    if not request_tokens or not business_tokens:
        return True
    return bool(request_tokens & business_tokens)


def _intent_text(intent: dict[str, Any] | None, key: str) -> str | None:
    if not intent:
        return None
    value = intent.get(key)
    return normalize_text(str(value)) if value is not None else None


def _intent_list(intent: dict[str, Any] | None, key: str) -> list[str]:
    if not intent:
        return []
    value = intent.get(key)
    if not isinstance(value, list):
        return []
    return [normalize_text(str(item)) for item in value if normalize_text(str(item))]


def _market_from_intent(intent: dict[str, Any] | None) -> str | None:
    location = _intent_text(intent, "location")
    country = _intent_text(intent, "country")
    if location and country and country.lower() not in location.lower():
        return f"{location}, {country}"
    return location or country


def _mapping_text(mapping: dict[str, Any], key: str) -> str | None:
    value = mapping.get(key)
    if isinstance(value, str) and value.strip():
        return normalize_text(value)
    return None


def _raw_text(raw: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    value = first_raw_text(nested_raw(raw), keys)
    return normalize_text(value) if value else None


def _query_from_raw(raw: dict[str, Any]) -> str | None:
    for layer in iter_raw_layers(raw):
        source_input = layer.get("source_input")
        if isinstance(source_input, dict):
            query = query_from_source_input(source_input)
            if query:
                return query
    return _raw_text(raw, ("compiled_query", "discovery_query", "query", "search_query"))


def _list_text(raw: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for layer in iter_raw_layers(raw):
        for key in keys:
            value = layer.get(key)
            if isinstance(value, list):
                items = [normalize_text(str(item)) for item in value if normalize_text(str(item))]
                if items:
                    return ", ".join(items)
    return None


def _join_parts(parts: list[str | None]) -> str:
    seen: set[str] = set()
    cleaned: list[str] = []
    for part in parts:
        normalized = normalize_text(part)
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(normalized)
    return ". ".join(cleaned)


def _meaningful_tokens(value: str) -> set[str]:
    key = semantic_key(value or "")
    if not key:
        return set()
    return {
        token
        for token in key.split()
        if len(token) >= 3 and token not in {"canada", "united", "states", "usa"}
    }
