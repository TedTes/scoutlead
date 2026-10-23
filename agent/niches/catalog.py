from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NicheSpec:
    key: str
    label: str
    slug: str
    niche_label: str
    category: str
    trade_terms: frozenset[str]
    excluded_terms: frozenset[str]


NICHE_CATALOG: dict[str, NicheSpec] = {
    "painters": NicheSpec(
        key="painters",
        label="Painters",
        slug="home_service_painting",
        niche_label="Painting contractors",
        category="painting contractors",
        trade_terms=frozenset({"paint", "painter", "painting", "decorating"}),
        excluded_terms=frozenset({"art gallery", "auto body", "paint store", "supplies"}),
    ),
    "hvac": NicheSpec(
        key="hvac",
        label="HVAC",
        slug="home_service_hvac",
        niche_label="HVAC contractors",
        category="HVAC contractors",
        trade_terms=frozenset(
            {"hvac", "heating", "cooling", "furnace", "air conditioning"}
        ),
        excluded_terms=frozenset({"supply", "supplies", "wholesale", "manufacturer"}),
    ),
    "roofers": NicheSpec(
        key="roofers",
        label="Roofers",
        slug="home_service_roofing",
        niche_label="Roofing contractors",
        category="roofing contractors",
        trade_terms=frozenset({"roof", "roofer", "roofing"}),
        excluded_terms=frozenset({"supply", "supplies", "truss", "waterproofing store"}),
    ),
    "plumbers": NicheSpec(
        key="plumbers",
        label="Plumbers",
        slug="home_service_plumbing",
        niche_label="Plumbing contractors",
        category="plumbing contractors",
        trade_terms=frozenset({"plumb", "plumber", "plumbing", "drain service"}),
        excluded_terms=frozenset({"supply", "supplies", "wholesale", "showroom"}),
    ),
    "electricians": NicheSpec(
        key="electricians",
        label="Electricians",
        slug="home_service_electrical",
        niche_label="Electrical contractors",
        category="electrical contractors",
        trade_terms=frozenset({"electric", "electrical", "electrician"}),
        excluded_terms=frozenset({"supply", "supplies", "utility", "wholesale"}),
    ),
    "cleaners": NicheSpec(
        key="cleaners",
        label="Cleaning services",
        slug="home_service_cleaning",
        niche_label="Residential cleaning services",
        category="residential cleaning services",
        trade_terms=frozenset(
            {
                "house cleaning",
                "home cleaning",
                "residential cleaning",
                "cleaning service",
                "maid",
                "cleaners",
            }
        ),
        excluded_terms=frozenset({"carpet", "duct", "dry clean", "laundry", "janitorial supply"}),
    ),
    "landscapers": NicheSpec(
        key="landscapers",
        label="Landscapers",
        slug="home_service_landscaping",
        niche_label="Landscaping contractors",
        category="landscaping contractors",
        trade_terms=frozenset({"landscape", "landscaping", "landscaper", "lawn care"}),
        excluded_terms=frozenset({"architect", "garden centre", "nursery", "supply"}),
    ),
    "pest_control": NicheSpec(
        key="pest_control",
        label="Pest control",
        slug="home_service_pest_control",
        niche_label="Pest control services",
        category="pest control services",
        trade_terms=frozenset(
            {"pest control", "exterminator", "extermination", "wildlife removal"}
        ),
        excluded_terms=frozenset({"supply", "supplies", "product", "manufacturer"}),
    ),
    "garage_doors": NicheSpec(
        key="garage_doors",
        label="Garage-door services",
        slug="home_service_garage_doors",
        niche_label="Garage-door services",
        category="garage-door repair and installation services",
        trade_terms=frozenset(
            {"garage door", "overhead door", "garage repair", "door installation"}
        ),
        excluded_terms=frozenset({"cabinet", "interior door", "lumber", "supply", "wholesale"}),
    ),
}


NICHE_BY_SLUG = {spec.slug: spec for spec in NICHE_CATALOG.values()}


def search_config_for_slug(slug: str | None) -> dict[str, list[str]]:
    spec = NICHE_BY_SLUG.get(slug or "")
    if spec is None:
        return {}
    return {
        "include_terms": sorted(spec.trade_terms),
        "exclude_terms": sorted(spec.excluded_terms),
    }


def niche_spec_for_slug(slug: str | None) -> NicheSpec | None:
    return NICHE_BY_SLUG.get(slug or "")
