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


def validate_google_places_query(query: str) -> None:
    normalized = " ".join((query or "").split())
    lower = normalized.lower()
    blocked_fragments = [" or ", " and ", "site:", "intitle:", "\"", "near me"]
    if not normalized:
        raise ValidationError(
            "discovery query is empty",
            {"source_provider": "google_places"},
        )
    if any(fragment in f" {lower} " for fragment in blocked_fragments):
        raise ValidationError(
            "discovery query is too broad for Google Places discovery",
            {
                "query": normalized,
                "required_shape": (
                    "Use a plain local-business query such as "
                    "'residential painters Toronto ON'. Do not use boolean operators, "
                    "site filters, or 'near me'."
                ),
            },
        )
    if "united states, canada" in lower or "united states canada" in lower:
        raise ValidationError(
            "discovery query needs a specific test market",
            {
                "query": normalized,
                "required_shape": (
                    "Include a concrete city, province/state, or country in the "
                    "product description, such as 'Toronto ON' or 'Austin TX'."
                ),
            },
        )
    if len(re.findall(r"[A-Za-z0-9]+", normalized)) < 3 or not has_geography_token(
        normalized
    ):
        raise ValidationError(
            "discovery query is missing a concrete market",
            {
                "query": normalized,
                "required_shape": (
                    "Use a business category plus geography, such as "
                    "'residential painters Toronto ON'."
                ),
            },
        )


def has_geography_token(query: str) -> bool:
    tokens = {token.upper() for token in re.findall(r"[A-Za-z]{2,}", query)}
    if tokens & _REGION_CODES:
        return True
    lower = query.lower()
    return any(term in lower for term in _GEOGRAPHY_TERMS)


_REGION_CODES = {
    "AB",
    "BC",
    "MB",
    "NB",
    "NL",
    "NS",
    "NT",
    "NU",
    "ON",
    "PE",
    "QC",
    "SK",
    "YT",
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
}

_GEOGRAPHY_TERMS = {
    "canada",
    "united states",
    "usa",
    "alberta",
    "british columbia",
    "manitoba",
    "new brunswick",
    "newfoundland",
    "nova scotia",
    "ontario",
    "prince edward island",
    "quebec",
    "saskatchewan",
    "yukon",
    "california",
    "texas",
    "florida",
    "new york",
    "pennsylvania",
    "illinois",
    "ohio",
    "georgia",
    "north carolina",
    "michigan",
    "new jersey",
    "virginia",
    "washington",
    "arizona",
    "massachusetts",
    "tennessee",
    "indiana",
    "missouri",
    "maryland",
    "wisconsin",
    "colorado",
    "minnesota",
    "south carolina",
    "alabama",
    "louisiana",
    "kentucky",
    "oregon",
    "oklahoma",
    "connecticut",
    "iowa",
    "mississippi",
    "arkansas",
    "kansas",
    "utah",
    "nevada",
    "new mexico",
    "west virginia",
    "nebraska",
    "idaho",
    "hawaii",
    "maine",
    "new hampshire",
    "rhode island",
    "montana",
    "delaware",
    "south dakota",
    "north dakota",
    "alaska",
    "vermont",
    "wyoming",
}
