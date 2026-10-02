from __future__ import annotations

import re

from business_facts.repository import BusinessFactKey
from business_index.schemas import (
    FactOperator,
    FactPredicate,
    OpportunityType,
    SearchContract,
)


NO_WEBSITE_PHRASES = ("no website", "without a website", "missing website")
UNAVAILABLE_WEBSITE_PHRASES = (
    "broken website",
    "dead website",
    "inactive website",
    "unavailable website",
    "parked website",
    "expired website",
)
QUOTE_FLOW_PHRASES = (
    "no quote",
    "missing quote",
    "without a quote",
    "no booking",
    "missing booking",
    "no clear quote",
    "no clear booking",
)
CONTACT_FLOW_PHRASES = ("no contact form", "missing contact form", "no clear contact flow")


def compile_search_contract(
    prompt: str | None,
    *,
    opportunity_type: OpportunityType,
) -> SearchContract:
    text = (prompt or "").casefold()
    all_of: list[FactPredicate] = []
    any_of: list[FactPredicate] = []
    unsupported: list[str] = []

    if "no website listed" in text or "website not listed" in text:
        any_of.append(
            FactPredicate(
                BusinessFactKey.WEBSITE_STATUS.value,
                FactOperator.IN,
                ("missing", "not_listed"),
            )
        )
    elif any(phrase in text for phrase in NO_WEBSITE_PHRASES):
        any_of.append(
            FactPredicate(
                BusinessFactKey.WEBSITE_STATUS.value,
                FactOperator.EQUALS,
                "missing",
            )
        )
    if any(phrase in text for phrase in UNAVAILABLE_WEBSITE_PHRASES):
        any_of.append(
            FactPredicate(
                BusinessFactKey.WEBSITE_STATUS.value,
                FactOperator.IN,
                ("unavailable", "parked"),
            )
        )
    if any(phrase in text for phrase in QUOTE_FLOW_PHRASES):
        any_of.append(
            FactPredicate(
                BusinessFactKey.QUOTE_OR_BOOKING_FORM_PRESENT.value,
                FactOperator.EQUALS,
                False,
            )
        )
    if any(phrase in text for phrase in CONTACT_FLOW_PHRASES):
        any_of.append(
            FactPredicate(
                BusinessFactKey.CONTACT_FORM_PRESENT.value,
                FactOperator.EQUALS,
                False,
            )
        )

    review_limit = _number_before(text, r"(?:fewer than|less than|under)\s+(\d+)\s+reviews?")
    if review_limit is not None:
        any_of.append(
            FactPredicate(
                BusinessFactKey.GOOGLE_REVIEW_COUNT.value,
                FactOperator.LESS_THAN,
                float(review_limit),
            )
        )
    elif "low review count" in text or "few reviews" in text:
        any_of.append(
            FactPredicate(
                BusinessFactKey.GOOGLE_REVIEW_COUNT.value,
                FactOperator.LESS_THAN,
                20.0,
            )
        )

    rating_limit = _number_before(
        text,
        r"(?:rating|rated)\s+(?:below|under|less than)\s+(\d+(?:\.\d+)?)",
        decimal=True,
    )
    if rating_limit is not None:
        any_of.append(
            FactPredicate(
                BusinessFactKey.GOOGLE_RATING.value,
                FactOperator.LESS_THAN,
                float(rating_limit),
            )
        )
    if "active business" in text or "active businesses" in text:
        all_of.append(
            FactPredicate(
                BusinessFactKey.BUSINESS_OPERATIONAL.value,
                FactOperator.EQUALS,
                True,
            )
        )

    if not any_of:
        any_of.extend(_fallback_opportunity_predicates(opportunity_type))

    if "independent" in text or "exclude chains" in text or "exclude franchises" in text:
        unsupported.append("independent_or_chain_status")
    if "director" in text and "exclude" in text:
        unsupported.append("directory_exclusion")
    if "exclude" in text and ("marketing agenc" in text or "web agenc" in text):
        unsupported.append("business_model_exclusion")

    return SearchContract(
        all_of=tuple(_unique_predicates(all_of)),
        any_of=tuple(_unique_predicates(any_of)),
        unsupported=tuple(dict.fromkeys(unsupported)),
    )


def _fallback_opportunity_predicates(
    opportunity_type: OpportunityType,
) -> list[FactPredicate]:
    if opportunity_type == OpportunityType.MISSING_WEBSITE:
        statuses = ("missing",)
    elif opportunity_type == OpportunityType.MISSING_OR_UNAVAILABLE_WEBSITE:
        statuses = ("missing", "unavailable", "parked")
    elif opportunity_type == OpportunityType.WEAK_OR_MISSING_WEBSITE:
        return [
            FactPredicate(
                BusinessFactKey.WEBSITE_STATUS.value,
                FactOperator.IN,
                ("missing", "unavailable", "parked"),
            ),
            FactPredicate(
                BusinessFactKey.QUOTE_OR_BOOKING_FORM_PRESENT.value,
                FactOperator.EQUALS,
                False,
            ),
            FactPredicate(
                BusinessFactKey.GOOGLE_REVIEW_COUNT.value,
                FactOperator.LESS_THAN,
                20.0,
            ),
        ]
    else:
        return []
    return [
        FactPredicate(
            BusinessFactKey.WEBSITE_STATUS.value,
            FactOperator.IN,
            statuses,
        )
    ]


def _number_before(text: str, pattern: str, *, decimal: bool = False) -> float | int | None:
    match = re.search(pattern, text)
    if match is None:
        return None
    return float(match.group(1)) if decimal else int(match.group(1))


def _unique_predicates(values: list[FactPredicate]) -> list[FactPredicate]:
    unique: dict[tuple, FactPredicate] = {}
    for value in values:
        raw_value = value.value if isinstance(value.value, tuple) else (value.value,)
        unique[(value.key, value.operator.value, *raw_value)] = value
    return list(unique.values())
