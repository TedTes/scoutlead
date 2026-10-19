from __future__ import annotations

from canonical.semantics import semantic_key


MARKET_CENTERS: dict[str, tuple[float, float]] = {
    "toronto": (43.6532, -79.3832),
    "north york": (43.7615, -79.4111),
    "scarborough": (43.7764, -79.2318),
    "etobicoke": (43.6205, -79.5132),
    "mississauga": (43.5890, -79.6441),
    "brampton": (43.7315, -79.7624),
    "vaughan": (43.8561, -79.5085),
    "markham": (43.8561, -79.3370),
}

MARKET_LOCATION_TERMS: dict[str, frozenset[str]] = {
    "toronto gta": frozenset(
        {
            "ajax",
            "aurora",
            "brampton",
            "burlington",
            "etobicoke",
            "markham",
            "milton",
            "mississauga",
            "newmarket",
            "north york",
            "oakville",
            "oshawa",
            "pickering",
            "richmond hill",
            "scarborough",
            "toronto",
            "vaughan",
            "whitby",
            "york",
        }
    ),
}


def market_center(city: str) -> tuple[float, float] | None:
    key = semantic_key(city)
    if key == "toronto gta":
        key = "toronto"
    return MARKET_CENTERS.get(key)


def market_matches_location(market_label: str, location: str) -> tuple[bool, list[str]]:
    market_key = semantic_key(market_label) or ""
    location_key = semantic_key(location) or ""
    terms = MARKET_LOCATION_TERMS.get(market_key)
    if terms is None:
        terms = frozenset(
            term
            for term in market_key.split()
            if len(term) >= 4 and term not in {"area", "greater", "region"}
        )
    matched = sorted(term for term in terms if term in location_key)
    return bool(matched), matched
