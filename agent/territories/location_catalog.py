from __future__ import annotations

from functools import lru_cache

import geonamescache


SUPPORTED_COUNTRIES = ("CA", "US", "MX")

CANADA_REGIONS = {
    "01": "Alberta",
    "02": "British Columbia",
    "03": "Manitoba",
    "04": "New Brunswick",
    "05": "Newfoundland and Labrador",
    "07": "Nova Scotia",
    "08": "Ontario",
    "09": "Prince Edward Island",
    "10": "Quebec",
    "11": "Saskatchewan",
    "12": "Yukon",
    "13": "Northwest Territories",
    "14": "Nunavut",
}


@lru_cache(maxsize=1)
def _catalog() -> geonamescache.GeonamesCache:
    return geonamescache.GeonamesCache()


def countries() -> list[dict[str, str]]:
    catalog = _catalog().get_countries()
    return [
        {"code": code, "name": str(catalog[code]["name"])}
        for code in SUPPORTED_COUNTRIES
    ]


def regions(country_code: str) -> list[dict[str, str]]:
    code = country_code.upper()
    if code == "CA":
        values = CANADA_REGIONS
    elif code == "US":
        values = {
            key: str(value["name"])
            for key, value in _catalog().get_us_states().items()
        }
    else:
        values = {}
    return [
        {"code": key, "name": name}
        for key, name in sorted(values.items(), key=lambda item: item[1])
    ]


def cities(country_code: str, region_code: str | None = None) -> list[dict]:
    country = country_code.upper()
    region = (region_code or "").upper()
    country_names = _catalog().get_countries()
    region_names = {item["code"]: item["name"] for item in regions(country)}
    selected: dict[tuple[str, str], dict] = {}
    for row in _catalog().get_cities().values():
        if row.get("countrycode") != country:
            continue
        admin_code = str(row.get("admin1code") or "").upper()
        if region and admin_code != region:
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        key = (name.casefold(), admin_code)
        current = selected.get(key)
        if (
            current is not None
            and int(current.get("population") or 0)
            >= int(row.get("population") or 0)
        ):
            continue
        region_name = region_names.get(admin_code)
        country_name = str((country_names.get(country) or {}).get("name") or country)
        label_parts = [name]
        if region_name:
            label_parts.append(region_name)
        label_parts.append(country_name)
        selected[key] = {
            "id": f"geonames:{row['geonameid']}",
            "name": name,
            "label": ", ".join(label_parts),
            "country_code": country.lower(),
            "region_code": admin_code or None,
            "region_name": region_name,
            "latitude": float(row["latitude"]),
            "longitude": float(row["longitude"]),
            "population": int(row.get("population") or 0),
        }
    return sorted(
        selected.values(),
        key=lambda item: (-item["population"], item["name"].casefold()),
    )
