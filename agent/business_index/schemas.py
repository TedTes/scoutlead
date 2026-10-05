from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class OpportunityType(StrEnum):
    ANY = "any"
    MISSING_WEBSITE = "missing_website"
    MISSING_OR_UNAVAILABLE_WEBSITE = "missing_or_unavailable_website"
    WEAK_OR_MISSING_WEBSITE = "weak_or_missing_website"


class FactOperator(StrEnum):
    EQUALS = "equals"
    IN = "in"
    LESS_THAN = "less_than"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"
    GREATER_THAN = "greater_than"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"


@dataclass(frozen=True)
class FactPredicate:
    key: str
    operator: FactOperator
    value: str | float | bool | tuple[str, ...]

    def as_dict(self) -> dict:
        value = list(self.value) if isinstance(self.value, tuple) else self.value
        return {"key": self.key, "operator": self.operator.value, "value": value}

    @classmethod
    def from_dict(cls, value: dict) -> "FactPredicate":
        raw_value = value["value"]
        if isinstance(raw_value, list):
            raw_value = tuple(raw_value)
        return cls(
            key=str(value["key"]),
            operator=FactOperator(str(value["operator"])),
            value=raw_value,
        )


@dataclass(frozen=True)
class SearchContract:
    all_of: tuple[FactPredicate, ...] = ()
    any_of: tuple[FactPredicate, ...] = ()
    ranking: tuple[FactPredicate, ...] = ()
    semantic_all_of: tuple[str, ...] = ()
    semantic_any_of: tuple[str, ...] = ()
    semantic_exclusions: tuple[str, ...] = ()
    contact_requirements: tuple[str, ...] = ()
    unsupported: tuple[str, ...] = ()
    version: int = 3

    def as_dict(self) -> dict:
        return {
            "version": self.version,
            "all_of": [predicate.as_dict() for predicate in self.all_of],
            "any_of": [predicate.as_dict() for predicate in self.any_of],
            "ranking": [predicate.as_dict() for predicate in self.ranking],
            "semantic_all_of": list(self.semantic_all_of),
            "semantic_any_of": list(self.semantic_any_of),
            "semantic_exclusions": list(self.semantic_exclusions),
            "contact_requirements": list(self.contact_requirements),
            "unsupported": list(self.unsupported),
        }

    @classmethod
    def from_dict(cls, value: dict | None) -> "SearchContract":
        raw = value or {}
        return cls(
            all_of=tuple(
                FactPredicate.from_dict(predicate)
                for predicate in raw.get("all_of", [])
            ),
            any_of=tuple(
                FactPredicate.from_dict(predicate)
                for predicate in raw.get("any_of", [])
            ),
            ranking=tuple(
                FactPredicate.from_dict(predicate)
                for predicate in raw.get("ranking", [])
            ),
            semantic_all_of=tuple(str(item) for item in raw.get("semantic_all_of", [])),
            semantic_any_of=tuple(str(item) for item in raw.get("semantic_any_of", [])),
            semantic_exclusions=tuple(
                str(item) for item in raw.get("semantic_exclusions", [])
            ),
            contact_requirements=tuple(
                str(item) for item in raw.get("contact_requirements", [])
            ),
            unsupported=tuple(str(item) for item in raw.get("unsupported", [])),
            version=int(raw.get("version") or 1),
        )

    @property
    def requires_semantic_evaluation(self) -> bool:
        return bool(
            self.semantic_all_of or self.semantic_any_of or self.semantic_exclusions
        )


@dataclass(frozen=True)
class BusinessIndexSearch:
    niche_id: str
    market_key: str
    opportunity_type: OpportunityType
    evidence_fresh_after: datetime
    result_count: int
    contract: SearchContract = field(default_factory=SearchContract)
    contract_hash: str = ""
