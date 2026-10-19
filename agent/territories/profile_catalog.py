from __future__ import annotations

from dataclasses import dataclass

from niches.catalog import NICHE_CATALOG


@dataclass(frozen=True)
class ProfileTradeSpec:
    key: str
    label: str
    niche_slug: str
    niche_label: str
    niche_category: str


PROFILE_TRADE_CATALOG = {
    key: ProfileTradeSpec(
        key=spec.key,
        label=spec.label,
        niche_slug=spec.slug,
        niche_label=spec.niche_label,
        niche_category=spec.category,
    )
    for key, spec in NICHE_CATALOG.items()
}


def profile_trade_spec(key: str) -> ProfileTradeSpec:
    return PROFILE_TRADE_CATALOG[key]


def profile_trade_label(keys: list[str]) -> str:
    return " + ".join(profile_trade_spec(key).label for key in keys)
