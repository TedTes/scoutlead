from __future__ import annotations

import re

from shared.errors import ValidationError


def normalize_places_region_code(value: str | None) -> str | None:
    normalized = (value or "").strip().upper()
    if normalized in {"CA", "US"}:
        return normalized

    lower = (value or "").strip().lower()
    if lower == "canada":
        return "CA"
    if lower in {"united states", "usa", "us", "u.s."}:
        return "US"
    return None


def build_local_business_query(
    *,
    business_category: str,
    location: str,
    fallback_query: str | None = None,
) -> str:
    category = _normalized(business_category)
    market = _normalized(location)
    validate_local_business_intent(
        business_category=category,
        location=market,
        query=fallback_query or f"{category} {market}",
    )

    return _normalized(f"{category} {market}")


def validate_local_business_intent(
    *,
    business_category: str,
    location: str,
    query: str | None = None,
) -> None:
    category = _normalized(business_category)
    market = _normalized(location)
    if not category:
        raise ValidationError(
            "search query needs a business category",
            {"user_message": "Describe the kind of businesses to find."},
        )
    if not market or _is_broad_market(market):
        raise ValidationError(
            "search query needs a specific market",
            {
                "query": _normalized(query or ""),
                "user_message": "Add a specific city or region to the search.",
            },
        )
    validate_google_places_query(query or f"{category} {market}")


def validate_google_places_query(query: str) -> None:
    normalized = _normalized(query)
    lower = normalized.lower()
    if not normalized:
        raise ValidationError(
            "search query is empty",
            {"user_message": "Describe the businesses and market to search."},
        )
    if _has_web_search_syntax(normalized):
        raise ValidationError(
            "search query is too broad",
            {
                "query": normalized,
                "user_message": (
                    "Use a plain business category and market, such as "
                    "'residential painters Toronto ON'."
                ),
                "required_shape": (
                    "Use a plain local-business query such as "
                    "'residential painters Toronto ON'. Do not use boolean operators, "
                    "site filters, or 'near me'."
                ),
            },
        )
    if _is_broad_market(lower):
        raise ValidationError(
            "search query needs a specific market",
            {
                "query": normalized,
                "user_message": "Add a specific city or region to the search.",
                "required_shape": (
                    "Include a concrete city, province/state, or country in the "
                    "product description, such as 'Toronto ON' or 'Austin TX'."
                ),
            },
        )
    if len(re.findall(r"[A-Za-z0-9]+", normalized)) < 3:
        raise ValidationError(
            "search query needs more detail",
            {
                "query": normalized,
                "user_message": (
                    "Use a business category plus a specific market."
                ),
                "required_shape": (
                    "Use a business category plus geography, such as "
                    "'residential painters Toronto ON'."
                ),
            },
        )


def _has_web_search_syntax(query: str) -> bool:
    lower = query.lower()
    if any(fragment in lower for fragment in ("site:", "intitle:", '"', "near me")):
        return True
    return bool(re.search(r"\b(?:AND|OR)\b", query))


def _is_broad_market(value: str) -> bool:
    normalized = _normalized(value).lower().replace(",", " ")
    normalized = " ".join(normalized.split())
    return normalized in {
        "canada",
        "united states",
        "usa",
        "us",
        "u s",
        "north america",
        "united states canada",
        "usa canada",
        "us canada",
    }


def _normalized(value: str | None) -> str:
    return " ".join((value or "").split())
