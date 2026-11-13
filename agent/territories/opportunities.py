from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OpportunityCriterion:
    key: str
    label: str
    description: str
    attribute_key: str
    weight: float = 1.0


# Saved-search opportunities are deliberately small and explicit.  They map
# directly to canonical business attributes; there is no database service
# catalog between the frontend criterion and the matcher.
OPPORTUNITY_CRITERIA: tuple[OpportunityCriterion, ...] = (
    OpportunityCriterion(
        key="website_availability",
        label="No website",
        description="Find active businesses without a verified owned website.",
        attribute_key="website_status",
    ),
    OpportunityCriterion(
        key="website_upgrade",
        label="Website needs improvement",
        description=(
            "Find businesses whose website has a measured, below-threshold "
            "website quality grade."
        ),
        attribute_key="website_quality_score",
    ),
)

OPPORTUNITY_BY_KEY = {criterion.key: criterion for criterion in OPPORTUNITY_CRITERIA}
OPPORTUNITY_BY_ATTRIBUTE = {
    criterion.attribute_key: criterion for criterion in OPPORTUNITY_CRITERIA
}
OPPORTUNITY_ATTRIBUTE_KEYS = frozenset(OPPORTUNITY_BY_ATTRIBUTE)


def normalize_opportunity_keys(keys: list[str]) -> list[str]:
    return list(dict.fromkeys(key for key in keys if key in OPPORTUNITY_BY_KEY))


def signal_keys_for_opportunities(keys: list[str]) -> list[str]:
    return list(
        dict.fromkeys(
            OPPORTUNITY_BY_KEY[key].attribute_key
            for key in keys
            if key in OPPORTUNITY_BY_KEY
        )
    )


def opportunity_options() -> list[dict]:
    return [
        {
            "key": criterion.key,
            "label": criterion.label,
            "description": criterion.description,
            "status": "active",
            "enabled": True,
            "signals": [
                {
                    "key": criterion.attribute_key,
                    "label": criterion.label,
                    "weight": criterion.weight,
                }
            ],
        }
        for criterion in OPPORTUNITY_CRITERIA
    ]
