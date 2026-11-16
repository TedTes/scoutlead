#!/usr/bin/env python3
"""Audit business identity overlap between ScoutLead environments.

The script has two deliberately read-only phases:

* ``extract`` runs inside an application container and emits compact business
  identity records plus dependency counts.
* ``compare`` runs locally against two extracts and emits a dry-run migration
  report. It never connects to or mutates either database.

Automatic matches are intentionally conservative. Provider identifiers and an
exact normalized name/address pair are strong identifiers. Domain and phone
matches are useful evidence but are reported as ambiguous unless supported by
another identity field, because franchises and multi-location businesses often
share them.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

from sqlalchemy import create_engine, inspect, text


PROVIDER_ID_KEYS = {
    "provider_business_id",
    "google_place_id",
    "place_id",
    "osm_id",
}

OBVIOUS_INVALID_PATTERNS = (
    re.compile(r"^find\s+.+\s+in\s+.+$", re.IGNORECASE),
    re.compile(r"^best\s+\d+\s+", re.IGNORECASE),
    re.compile(r"^top\s+\d+\s+", re.IGNORECASE),
    re.compile(r"\|\s*(houzz|yelp|reddit|yellow pages|homestars)\s*$", re.IGNORECASE),
    re.compile(r"\b(search results?|near me)\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class Identity:
    business_id: str
    name: str
    normalized_name: str
    domain: str | None
    phone: str | None
    address: str | None
    latitude: float | None
    longitude: float | None
    provider_ids: tuple[str, ...]
    business_operational: bool | None
    source_providers: tuple[str, ...]
    status: str
    is_directory: bool | None
    attribute_count: int
    membership_count: int
    contact_count: int
    lead_count: int
    audience_result_count: int

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Identity":
        return cls(
            business_id=str(value["id"]),
            name=str(value.get("display_name") or ""),
            normalized_name=_norm_text(
                value.get("normalized_name") or value.get("display_name")
            ),
            domain=_norm_domain(value.get("domain") or value.get("website_url")),
            phone=_norm_phone(value.get("phone")),
            address=_norm_text(value.get("address")) or None,
            latitude=_float_or_none(value.get("latitude")),
            longitude=_float_or_none(value.get("longitude")),
            provider_ids=tuple(sorted(set(value.get("provider_ids") or []))),
            business_operational=value.get("business_operational"),
            source_providers=tuple(sorted(set(value.get("source_providers") or []))),
            status=str(value.get("status") or "unknown"),
            is_directory=value.get("is_directory"),
            attribute_count=int(value.get("attribute_count") or 0),
            membership_count=int(value.get("membership_count") or 0),
            contact_count=int(value.get("contact_count") or 0),
            lead_count=int(value.get("lead_count") or 0),
            audience_result_count=int(value.get("audience_result_count") or 0),
        )


def _norm_text(value: Any) -> str:
    if value is None:
        return ""
    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    return " ".join(
        "".join(character if character.isalnum() else " " for character in normalized).split()
    )


def _norm_domain(value: Any) -> str | None:
    if not value:
        return None
    raw = str(value).strip().casefold()
    parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").removeprefix("www.").rstrip(".")
    return host or None


def _norm_phone(value: Any) -> str | None:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) > 10 and digits.startswith("1"):
        digits = digits[-10:]
    return digits if len(digits) >= 7 else None


def _provider_family(provider: str, external_id: str) -> str:
    if provider in {"google places", "google places seed"} or external_id.startswith("ChIJ"):
        return "google_places"
    if provider == "openstreetmap" or external_id.startswith("osm:"):
        return "openstreetmap"
    return provider.replace(" ", "_")


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _table_count_sql(inspector: Any, table: str, business_id: str) -> str:
    if table not in inspector.get_table_names():
        return "0"
    columns = {column["name"] for column in inspector.get_columns(table)}
    if "business_id" not in columns:
        return "0"
    safe_id = business_id.replace("'", "''")
    return f"(SELECT count(*) FROM {table} WHERE business_id = '{safe_id}')"


def extract() -> dict[str, Any]:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    engine = create_engine(database_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    required = {"businesses", "business_attributes"}
    missing = sorted(required - tables)
    if missing:
        raise SystemExit(f"Missing required tables: {', '.join(missing)}")

    with engine.connect() as connection:
        businesses = [
            dict(row)
            for row in connection.execute(
                text(
                    """
                    SELECT id, display_name, normalized_name, website_url, domain,
                           phone, address, latitude, longitude, status, is_directory,
                           first_seen_at, last_seen_at
                    FROM businesses
                    ORDER BY id
                    """
                )
            ).mappings()
        ]
        attributes = [
            dict(row)
            for row in connection.execute(
                text(
                    """
                    SELECT business_id, attribute_key, value_text, value_boolean, source_provider,
                           source_external_id
                    FROM business_attributes
                    WHERE attribute_key = ANY(:keys)
                       OR source_external_id IS NOT NULL
                    """
                ),
                {
                    "keys": sorted(
                        PROVIDER_ID_KEYS
                        | {"business_operational", "trade_category", "website_status"}
                    )
                },
            ).mappings()
        ]

        provider_ids: dict[str, set[str]] = defaultdict(set)
        source_providers: dict[str, set[str]] = defaultdict(set)
        business_operational: dict[str, bool] = {}
        for row in attributes:
            business_id = str(row["business_id"])
            provider = _norm_text(row.get("source_provider")) or "unknown"
            if provider != "unknown":
                source_providers[business_id].add(provider)
            external_id = str(row.get("source_external_id") or "").strip()
            trusted_discovery_provider = provider in {
                "google places",
                "google places seed",
                "openstreetmap",
            }
            trusted_external_id = external_id.startswith("ChIJ") or external_id.startswith("osm:")
            if external_id and trusted_discovery_provider and trusted_external_id:
                provider_ids[business_id].add(
                    f"{_provider_family(provider, external_id)}:{external_id}"
                )
            if row.get("attribute_key") in PROVIDER_ID_KEYS and row.get("value_text"):
                value_text = str(row["value_text"]).strip()
                provider_ids[business_id].add(
                    f"{_provider_family(provider, value_text)}:{value_text}"
                )
            if row.get("attribute_key") == "business_operational":
                raw_value = row.get("value_boolean")
                if raw_value is None:
                    raw_value = row.get("value_text")
                if isinstance(raw_value, bool):
                    business_operational[business_id] = raw_value
                elif raw_value is not None:
                    business_operational[business_id] = str(raw_value).casefold() in {
                        "true",
                        "1",
                        "yes",
                        "operational",
                    }

        counts: dict[str, dict[str, int]] = defaultdict(dict)
        for table in (
            "business_attributes",
            "business_niche_memberships",
            "contacts",
            "leads",
            "audience_results",
        ):
            if table not in tables:
                continue
            columns = {column["name"] for column in inspector.get_columns(table)}
            if "business_id" not in columns:
                continue
            for row in connection.execute(
                text(
                    f"SELECT business_id, count(*) AS count FROM {table} "
                    "WHERE business_id IS NOT NULL GROUP BY business_id"
                )
            ).mappings():
                counts[str(row["business_id"])][table] = int(row["count"])

        records = []
        for business in businesses:
            business_id = str(business["id"])
            dependency_counts = counts.get(business_id, {})
            records.append(
                {
                    **business,
                    "first_seen_at": _iso(business.get("first_seen_at")),
                    "last_seen_at": _iso(business.get("last_seen_at")),
                    "provider_ids": sorted(provider_ids.get(business_id, set())),
                    "business_operational": business_operational.get(business_id),
                    "source_providers": sorted(source_providers.get(business_id, set())),
                    "attribute_count": dependency_counts.get("business_attributes", 0),
                    "membership_count": dependency_counts.get(
                        "business_niche_memberships", 0
                    ),
                    "contact_count": dependency_counts.get("contacts", 0),
                    "lead_count": dependency_counts.get("leads", 0),
                    "audience_result_count": dependency_counts.get(
                        "audience_results", 0
                    ),
                }
            )

    return {
        "schema_version": 1,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "database_identity": _database_identity(database_url),
        "business_count": len(records),
        "businesses": records,
    }


def _database_identity(database_url: str) -> str:
    parsed = urlsplit(database_url.replace("postgresql+psycopg", "postgresql"))
    return f"{parsed.hostname or 'unknown'}/{parsed.path.lstrip('/') or 'unknown'}"


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


class UnionFind:
    def __init__(self, ids: Iterable[str]) -> None:
        self.parent = {item: item for item in ids}

    def find(self, item: str) -> str:
        parent = self.parent[item]
        if parent != item:
            self.parent[item] = self.find(parent)
        return self.parent[item]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def _strong_keys(item: Identity) -> set[str]:
    result: set[str] = set()
    if item.normalized_name and item.address:
        result.add(f"name_address:{item.normalized_name}|{item.address}")
    if item.normalized_name and item.latitude is not None and item.longitude is not None:
        result.add(
            "name_coordinate:"
            f"{item.normalized_name}|{round(item.latitude, 4)}|{round(item.longitude, 4)}"
        )
    return result


def _weak_keys(item: Identity) -> set[str]:
    result: set[str] = set()
    result.update(f"provider:{value}" for value in item.provider_ids)
    if item.domain:
        result.add(f"domain:{item.domain}")
    if item.phone:
        result.add(f"phone:{item.phone}")
    if item.normalized_name:
        result.add(f"name:{item.normalized_name}")
    return result


def _groups(items: list[Identity], *, strong: bool) -> list[list[str]]:
    union = UnionFind(item.business_id for item in items)
    by_key: dict[str, list[str]] = defaultdict(list)
    for item in items:
        keys = _strong_keys(item) if strong else _weak_keys(item)
        for key in keys:
            by_key[key].append(item.business_id)
    for ids in by_key.values():
        first = ids[0]
        for business_id in ids[1:]:
            union.union(first, business_id)
    grouped: dict[str, list[str]] = defaultdict(list)
    for item in items:
        grouped[union.find(item.business_id)].append(item.business_id)
    return [sorted(ids) for ids in grouped.values() if len(ids) > 1]


def _invalid_reason(item: Identity) -> str | None:
    if item.is_directory is True:
        return "directory flag is true"
    if item.status in {"deleted", "retired"}:
        return f"business status is {item.status}"
    if item.business_operational is False:
        return "business_operational is false"
    if not item.normalized_name:
        return "missing business name"
    for pattern in OBVIOUS_INVALID_PATTERNS:
        if pattern.search(item.name):
            return f"name matches non-business pattern: {pattern.pattern}"
    if (
        not item.provider_ids
        and not item.domain
        and not item.phone
        and not item.address
        and item.attribute_count == 0
    ):
        return "no stable identity or supporting attributes"
    return None


def _index(items: list[Identity], key_fn: Any) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for item in items:
        for key in key_fn(item):
            result[key].add(item.business_id)
    return result


def _match_ids(
    item: Identity,
    production_by_id: dict[str, Identity],
    strong_index: dict[str, set[str]],
    weak_index: dict[str, set[str]],
) -> tuple[set[str], set[str]]:
    strong: set[str] = set()
    weak: set[str] = set()
    for key in _strong_keys(item):
        strong.update(strong_index.get(key, set()))
    for key in _weak_keys(item):
        weak.update(weak_index.get(key, set()))
    # A shared provider ID is only an automatic match when the identity fields
    # remain compatible. Provider collisions have occurred in historical data.
    for candidate_id in list(weak):
        candidate = production_by_id[candidate_id]
        shared_provider = set(item.provider_ids).intersection(candidate.provider_ids)
        if not shared_provider:
            continue
        name_similarity = SequenceMatcher(
            None, item.normalized_name, candidate.normalized_name
        ).ratio()
        same_address = bool(item.address and item.address == candidate.address)
        close_coordinate = _coordinates_close(item, candidate)
        if name_similarity >= 0.72 and (same_address or close_coordinate or name_similarity >= 0.9):
            strong.add(candidate_id)
    return strong, weak - strong


def _coordinates_close(left: Identity, right: Identity) -> bool:
    if (
        left.latitude is None
        or left.longitude is None
        or right.latitude is None
        or right.longitude is None
    ):
        return False
    return (
        abs(left.latitude - right.latitude) <= 0.0003
        and abs(left.longitude - right.longitude) <= 0.0003
    )


def compare(dev_payload: dict[str, Any], prod_payload: dict[str, Any]) -> dict[str, Any]:
    dev = [Identity.from_dict(row) for row in dev_payload["businesses"]]
    prod = [Identity.from_dict(row) for row in prod_payload["businesses"]]
    prod_by_id = {item.business_id: item for item in prod}
    prod_strong = _index(prod, _strong_keys)
    prod_weak = _index(prod, _weak_keys)

    invalid: list[dict[str, Any]] = []
    existing: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    for item in dev:
        reason = _invalid_reason(item)
        if reason:
            invalid.append({"dev_business_id": item.business_id, "name": item.name, "reason": reason})
            continue
        strong, weak = _match_ids(item, prod_by_id, prod_strong, prod_weak)
        summary = {
            "dev_business_id": item.business_id,
            "name": item.name,
            "domain": item.domain,
            "phone": item.phone,
            "attribute_count": item.attribute_count,
            "membership_count": item.membership_count,
            "contact_count": item.contact_count,
            "business_operational": item.business_operational,
            "source_providers": list(item.source_providers),
            "lead_count": item.lead_count,
            "audience_result_count": item.audience_result_count,
        }
        if strong:
            existing.append({**summary, "production_business_ids": sorted(strong)})
        elif weak:
            ambiguous.append({**summary, "possible_production_business_ids": sorted(weak)})
        elif _strong_keys(item) or item.provider_ids:
            candidates.append(summary)
        else:
            unresolved.append({**summary, "reason": "no strong stable identity"})

    strong_groups = _groups(dev, strong=True)
    weak_groups = _groups(dev, strong=False)
    dev_by_id = {item.business_id: item for item in dev}
    candidate_ids = {item["dev_business_id"] for item in candidates}
    invalid_ids = {item["dev_business_id"] for item in invalid}

    representative_sample = _representative_sample(
        [
            item
            for item in dev
            if item.business_id not in invalid_ids
        ],
        limit=96,
    )

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "dry_run_read_only",
        "rules": {
            "automatic_match": [
                "same normalized name and address",
                "same normalized name and coordinates rounded to 4 decimals",
                "same provider identifier plus compatible name and location",
            ],
            "ambiguous_only": [
                "domain alone",
                "phone alone",
                "name alone",
            ],
            "mutation_policy": "No rows were inserted, updated, merged, or deleted.",
        },
        "source_counts": {
            "dev_business_records": len(dev),
            "production_business_records": len(prod),
        },
        "classification_counts": {
            "already_in_production_strong_match": len(existing),
            "new_production_candidates": len(candidates),
            "ambiguous_cross_environment_matches": len(ambiguous),
            "invalid_records": len(invalid),
            "unresolved_without_strong_identity": len(unresolved),
            "dev_strong_duplicate_groups": len(strong_groups),
            "dev_weak_overlap_groups": len(weak_groups),
            "new_candidates_in_dev_strong_duplicate_groups": sum(
                1
                for group in strong_groups
                if len(candidate_ids.intersection(group)) > 1
            ),
        },
        "already_in_production": existing,
        "new_production_candidates": candidates,
        "ambiguous_cross_environment_matches": ambiguous,
        "invalid_records": invalid,
        "unresolved_without_strong_identity": unresolved,
        "dev_strong_duplicate_groups": [
            {
                "business_ids": group,
                "names": sorted({dev_by_id[item].name for item in group}),
            }
            for group in strong_groups
        ],
        "dev_weak_overlap_groups": [
            {
                "business_ids": group,
                "names": sorted({dev_by_id[item].name for item in group}),
            }
            for group in weak_groups
        ],
        "proposed_dev_sample": representative_sample,
    }


def _representative_sample(items: list[Identity], *, limit: int) -> list[str]:
    """Choose a deterministic, varied sample without claiming quality."""
    buckets: dict[str, list[Identity]] = defaultdict(list)
    for item in sorted(items, key=lambda value: value.business_id):
        identity_shape = ":".join(
            [
                "domain" if item.domain else "no_domain",
                "phone" if item.phone else "no_phone",
                "address" if item.address else "no_address",
                "workflow" if item.lead_count or item.audience_result_count else "catalog",
            ]
        )
        buckets[identity_shape].append(item)

    selected: list[str] = []
    while len(selected) < limit and buckets:
        exhausted = []
        for key in sorted(buckets):
            bucket = buckets[key]
            if bucket:
                selected.append(bucket.pop(0).business_id)
                if len(selected) >= limit:
                    break
            if not bucket:
                exhausted.append(key)
        for key in exhausted:
            buckets.pop(key, None)
    return selected


def _load_payload(path: str) -> dict[str, Any]:
    raw = Path(path).read_text(encoding="utf-8")
    # Railway may prefix a connection notice. Keep the last JSON object line.
    for line in reversed(raw.splitlines()):
        candidate = line.strip()
        if candidate.startswith("{"):
            return json.loads(candidate)
    return json.loads(raw)


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("extract")
    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("--dev", required=True)
    compare_parser.add_argument("--production", required=True)
    args = parser.parse_args()

    if args.command == "extract":
        payload = extract()
    else:
        payload = compare(
            _load_payload(args.dev),
            _load_payload(args.production),
        )
    json.dump(payload, sys.stdout, separators=(",", ":"), default=str)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
