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


def market_center(city: str) -> tuple[float, float] | None:
    return MARKET_CENTERS.get(semantic_key(city))
