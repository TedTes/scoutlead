from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProfileTradeSpec:
    key: str
    label: str
    niche_slug: str
    niche_label: str
    niche_category: str


PROFILE_TRADE_CATALOG = {
    "painters": ProfileTradeSpec(
        key="painters",
        label="Painters",
        niche_slug="home_service_painting",
        niche_label="Painting contractors",
        niche_category="painting contractors",
    ),
    "hvac": ProfileTradeSpec(
        key="hvac",
        label="HVAC",
        niche_slug="home_service_hvac",
        niche_label="HVAC contractors",
        niche_category="HVAC contractors",
    ),
    "roofers": ProfileTradeSpec(
        key="roofers",
        label="Roofers",
        niche_slug="home_service_roofing",
        niche_label="Roofing contractors",
        niche_category="roofing contractors",
    ),
    "plumbers": ProfileTradeSpec(
        key="plumbers",
        label="Plumbers",
        niche_slug="home_service_plumbing",
        niche_label="Plumbing contractors",
        niche_category="plumbing contractors",
    ),
    "electricians": ProfileTradeSpec(
        key="electricians",
        label="Electricians",
        niche_slug="home_service_electrical",
        niche_label="Electrical contractors",
        niche_category="electrical contractors",
    ),
}


def profile_trade_spec(key: str) -> ProfileTradeSpec:
    return PROFILE_TRADE_CATALOG[key]


def profile_trade_label(keys: list[str]) -> str:
    return " + ".join(profile_trade_spec(key).label for key in keys)
