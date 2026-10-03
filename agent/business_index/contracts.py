from __future__ import annotations

import hashlib
import json
from typing import Any

from business_facts.repository import BusinessFactKey
from business_index.schemas import FactOperator, FactPredicate, SearchContract
from source_requests.schemas import (
    SearchCriterionMode,
    SearchIntentCriterion,
    SourceRequestIntent,
)


SUPPORTED_FACTS: dict[str, dict[str, Any]] = {
    BusinessFactKey.WEBSITE_STATUS.value: {
        "type": "enum",
        "values": ["present", "missing", "not_listed", "unavailable", "parked", "unknown"],
        "operators": ["equals", "in"],
    },
    BusinessFactKey.QUOTE_OR_BOOKING_FORM_PRESENT.value: {
        "type": "boolean",
        "operators": ["equals"],
    },
    BusinessFactKey.CONTACT_FORM_PRESENT.value: {
        "type": "boolean",
        "operators": ["equals"],
    },
    BusinessFactKey.GOOGLE_RATING.value: {
        "type": "number",
        "operators": ["less_than", "less_than_or_equal", "greater_than", "greater_than_or_equal"],
    },
    BusinessFactKey.GOOGLE_REVIEW_COUNT.value: {
        "type": "number",
        "operators": ["less_than", "less_than_or_equal", "greater_than", "greater_than_or_equal"],
    },
    BusinessFactKey.BUSINESS_OPERATIONAL.value: {
        "type": "boolean",
        "operators": ["equals"],
    },
}

SUPPORTED_CONTACT_REQUIREMENTS = {"email", "phone", "any_contact"}


def compile_search_contract(intent: SourceRequestIntent) -> SearchContract:
    all_of: list[FactPredicate] = []
    any_of: list[FactPredicate] = []
    semantic_all_of: list[str] = []
    semantic_any_of: list[str] = []
    semantic_exclusions: list[str] = []
    unsupported: list[str] = []

    for criterion in intent.criteria:
        predicate = _known_fact_predicate(criterion)
        if predicate is not None:
            if criterion.mode == SearchCriterionMode.ALTERNATIVE:
                any_of.append(predicate)
            elif criterion.mode == SearchCriterionMode.REQUIRED:
                all_of.append(predicate)
            else:
                semantic_exclusions.append(criterion.description)
            continue
        if criterion.fact_key:
            unsupported.append(f"{criterion.description} ({criterion.fact_key})")
        if criterion.mode == SearchCriterionMode.REQUIRED:
            semantic_all_of.append(criterion.description)
        elif criterion.mode == SearchCriterionMode.ALTERNATIVE:
            semantic_any_of.append(criterion.description)
        else:
            semantic_exclusions.append(criterion.description)

    contacts = []
    for requirement in intent.contact_requirements:
        normalized = requirement.strip().lower()
        if normalized in SUPPORTED_CONTACT_REQUIREMENTS:
            contacts.append(normalized)
        else:
            unsupported.append(f"contact requirement: {requirement}")

    return SearchContract(
        all_of=tuple(_unique_predicates(all_of)),
        any_of=tuple(_unique_predicates(any_of)),
        semantic_all_of=tuple(dict.fromkeys(semantic_all_of)),
        semantic_any_of=tuple(dict.fromkeys(semantic_any_of)),
        semantic_exclusions=tuple(dict.fromkeys(semantic_exclusions)),
        contact_requirements=tuple(dict.fromkeys(contacts)),
        unsupported=tuple(dict.fromkeys(unsupported)),
    )


def search_contract_hash(
    intent: SourceRequestIntent,
    contract: SearchContract,
    *,
    evidence_max_age_days: int = 30,
) -> str:
    payload = {
        "intent_schema_version": intent.schema_version,
        "business_category": intent.business_category.strip().casefold(),
        "location": intent.location.strip().casefold(),
        "included_subcategories": sorted(
            value.strip().casefold() for value in intent.included_subcategories if value.strip()
        ),
        "evidence_max_age_days": evidence_max_age_days,
        "contract": contract.as_dict(),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def fact_catalog_for_prompt() -> dict[str, dict[str, Any]]:
    return SUPPORTED_FACTS


def _known_fact_predicate(criterion: SearchIntentCriterion) -> FactPredicate | None:
    if not criterion.fact_key or criterion.fact_key not in SUPPORTED_FACTS:
        return None
    definition = SUPPORTED_FACTS[criterion.fact_key]
    operator_value = (criterion.operator or "").strip().lower()
    if operator_value not in definition["operators"]:
        return None
    try:
        operator = FactOperator(operator_value)
    except ValueError:
        return None
    value = criterion.value
    if operator == FactOperator.IN:
        if not isinstance(value, list) or not value:
            return None
        normalized_value: str | float | bool | tuple[str, ...] = tuple(str(item) for item in value)
    elif definition["type"] == "boolean":
        if not isinstance(value, bool):
            return None
        normalized_value = value
    elif definition["type"] == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        normalized_value = float(value)
    else:
        if not isinstance(value, str):
            return None
        normalized_value = value
    if definition["type"] == "enum":
        allowed = set(definition.get("values") or [])
        values = normalized_value if isinstance(normalized_value, tuple) else (normalized_value,)
        if any(item not in allowed for item in values):
            return None
    return FactPredicate(criterion.fact_key, operator, normalized_value)


def _unique_predicates(values: list[FactPredicate]) -> list[FactPredicate]:
    unique: dict[tuple, FactPredicate] = {}
    for value in values:
        raw_value = value.value if isinstance(value.value, tuple) else (value.value,)
        unique[(value.key, value.operator.value, *raw_value)] = value
    return list(unique.values())
