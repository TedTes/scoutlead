#!/usr/bin/env python3
"""Promote validated canonical business data between ScoutLead databases.

The source export contains public business records, contacts, observations, and
niche memberships. Derived facts are rebuilt in the target from the copied
observations. Users, workspaces, leads, audiences, and outreach data are never
included.

Examples:
    python scripts/migrate_business_index.py export --output /tmp/businesses.jsonl
    python scripts/migrate_business_index.py plan --input /tmp/businesses.jsonl
    python scripts/migrate_business_index.py import --input /tmp/businesses.jsonl --apply
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session


ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from app.config import get_settings  # noqa: E402
from business_facts.service import reconcile_business_facts  # noqa: E402
from canonical.normalization import (  # noqa: E402
    normalize_business_name,
    normalize_domain,
    normalize_email,
    normalize_phone,
)
from db.models import (  # noqa: E402
    BusinessModel,
    BusinessNicheMembershipModel,
    ContactModel,
    NicheModel,
    SourceObservationModel,
    ValidationResultModel,
)
from db.session import Database  # noqa: E402
from shared.utils import new_id, utcnow  # noqa: E402


REQUIRED_VALIDATIONS = {"identity", "business_identity", "trade", "location"}
SHARED_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "linktr.ee",
}


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    database = Database(get_settings().database_url)
    with database.session_factory() as session:
        if args.command == "export":
            summary = export_records(session, args.output)
        else:
            records = _read_records(args.input)
            summary = import_records(
                session,
                records,
                apply=args.command == "import" and args.apply,
                limit=args.limit,
                commit_every=args.commit_every,
            )
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


def export_records(session: Session, output: Path) -> dict[str, Any]:
    accepted_ids, validation_summary = validated_business_ids(session)
    candidate_businesses = list(
        session.scalars(
            select(BusinessModel)
            .where(
                BusinessModel.id.in_(accepted_ids),
                BusinessModel.status == "active",
            )
            .order_by(BusinessModel.id)
        )
    )
    business_ids = [business.id for business in candidate_businesses]
    contacts = _group_by_business(
        session.scalars(
            select(ContactModel).where(ContactModel.business_id.in_(business_ids))
        ),
    )
    observations = _group_by_business(
        session.scalars(
            select(SourceObservationModel)
            .where(SourceObservationModel.business_id.in_(business_ids))
            .order_by(SourceObservationModel.observed_at, SourceObservationModel.id)
        ),
    )
    corrupt_business_ids = {
        business.id
        for business in candidate_businesses
        if _is_corrupt_identity_cluster(observations.get(business.id, []))
    }
    businesses = [
        business
        for business in candidate_businesses
        if business.id not in corrupt_business_ids
    ]
    business_ids = [business.id for business in businesses]
    memberships = _group_by_business(
        session.scalars(
            select(BusinessNicheMembershipModel).where(
                BusinessNicheMembershipModel.business_id.in_(business_ids)
            )
        ),
    )
    niche_ids = {
        membership.niche_id
        for rows in memberships.values()
        for membership in rows
    }
    niches = {
        niche.id: niche
        for niche in session.scalars(select(NicheModel).where(NicheModel.id.in_(niche_ids)))
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    observation_count = 0
    contact_count = 0
    membership_count = 0
    with output.open("w", encoding="utf-8") as handle:
        for business in businesses:
            business_contacts = contacts.get(business.id, [])
            business_observations = observations.get(business.id, [])
            business_memberships = memberships.get(business.id, [])
            record = {
                "version": 1,
                "business": _business_payload(business),
                "contacts": [_contact_payload(row) for row in business_contacts],
                "observations": [
                    _observation_payload(row) for row in business_observations
                ],
                "memberships": [
                    _membership_payload(row, niches[row.niche_id])
                    for row in business_memberships
                    if row.niche_id in niches
                ],
            }
            handle.write(json.dumps(record, sort_keys=True, default=_json_default))
            handle.write("\n")
            observation_count += len(business_observations)
            contact_count += len(business_contacts)
            membership_count += len(business_memberships)

    return {
        "output": str(output),
        "businesses_exported": len(businesses),
        "contacts_exported": contact_count,
        "observations_exported": observation_count,
        "memberships_exported": membership_count,
        "corrupt_identity_clusters_excluded": len(corrupt_business_ids),
        "corrupt_identity_cluster_ids": sorted(corrupt_business_ids),
        "validation": validation_summary,
    }


def validated_business_ids(session: Session) -> tuple[set[str], dict[str, int]]:
    latest: dict[tuple[str, str], ValidationResultModel] = {}
    for result in session.scalars(
        select(ValidationResultModel).order_by(ValidationResultModel.observed_at)
    ):
        if result.validation_type in REQUIRED_VALIDATIONS:
            latest[(result.business_id, result.validation_type)] = result
    statuses: dict[str, dict[str, str]] = defaultdict(dict)
    for (business_id, validation_type), result in latest.items():
        statuses[business_id][validation_type] = result.status
    accepted = {
        business_id
        for business_id, values in statuses.items()
        if set(values) == REQUIRED_VALIDATIONS
        and all(status == "passed" for status in values.values())
    }
    return accepted, {
        "businesses_with_validation": len(statuses),
        "businesses_passing_all_required": len(accepted),
        "businesses_rejected_or_incomplete": len(statuses) - len(accepted),
    }


def _is_corrupt_identity_cluster(observations: list[Any]) -> bool:
    provider_identities = {
        (str(_value(row, "source") or ""), str(_value(row, "external_id") or ""))
        for row in observations
        if _value(row, "external_id")
    }
    return len(provider_identities) > 10 or len(observations) > 100


def _value(row: Any, key: str) -> Any:
    return row.get(key) if isinstance(row, dict) else getattr(row, key, None)


class IdentityIndex:
    def __init__(self) -> None:
        self.external: dict[tuple[str, str], set[str]] = defaultdict(set)
        self.domain: dict[str, set[str]] = defaultdict(set)
        self.phone: dict[str, set[str]] = defaultdict(set)
        self.name_market: dict[tuple[str, str], set[str]] = defaultdict(set)

    @classmethod
    def from_session(cls, session: Session) -> "IdentityIndex":
        index = cls()
        businesses = {row.id: row for row in session.scalars(select(BusinessModel))}
        for business in businesses.values():
            index.add_business(business.id, _business_payload(business), [])
        for observation in session.scalars(select(SourceObservationModel)):
            if observation.external_id:
                index.external[(observation.source, observation.external_id)].add(
                    observation.business_id
                )
        return index

    def add_business(
        self,
        business_id: str,
        business: dict[str, Any],
        observations: list[dict[str, Any]],
    ) -> None:
        domain = normalize_domain(business.get("domain") or business.get("website_url"))
        if domain and domain not in SHARED_DOMAINS:
            self.domain[domain].add(business_id)
        phone = normalize_phone(business.get("phone"))
        if phone:
            self.phone[phone].add(business_id)
        name = normalize_business_name(str(business.get("display_name") or ""))
        market = str(business.get("market_key") or "").strip().lower()
        if name and market:
            self.name_market[(name, market)].add(business_id)
        for observation in observations:
            source = str(observation.get("source") or "")
            external_id = str(observation.get("external_id") or "")
            if source and external_id:
                self.external[(source, external_id)].add(business_id)

    def resolve(self, record: dict[str, Any]) -> tuple[str, str | None]:
        business = record["business"]
        observations = record.get("observations") or []
        external = set()
        for observation in observations:
            source = str(observation.get("source") or "")
            external_id = str(observation.get("external_id") or "")
            if source and external_id:
                external.update(self.external.get((source, external_id), set()))
        domain_value = normalize_domain(
            business.get("domain") or business.get("website_url")
        )
        domain = (
            set(self.domain.get(domain_value, set()))
            if domain_value and domain_value not in SHARED_DOMAINS
            else set()
        )
        phone_value = normalize_phone(business.get("phone"))
        phone = set(self.phone.get(phone_value, set())) if phone_value else set()
        name = normalize_business_name(str(business.get("display_name") or ""))
        market = str(business.get("market_key") or "").strip().lower()
        name_market = set(self.name_market.get((name, market), set())) if name and market else set()

        unique_signals = [
            next(iter(values))
            for values in (external, phone, name_market)
            if len(values) == 1
        ]
        if unique_signals:
            candidate = unique_signals[0]
            if any(value != candidate for value in unique_signals[1:]):
                return "conflict", None
            if domain and candidate not in domain and len(domain) == 1:
                return "conflict", None
            return "matched", candidate
        if len(domain) == 1:
            return "matched", next(iter(domain))
        if external or phone or domain or name_market:
            return "conflict", None
        return "new", None


def import_records(
    session: Session,
    records: list[dict[str, Any]],
    *,
    apply: bool,
    limit: int | None,
    commit_every: int,
) -> dict[str, Any]:
    selected = records[:limit] if limit is not None else records
    index = IdentityIndex.from_session(session)
    summary: dict[str, Any] = {
        "dry_run": not apply,
        "records_read": len(selected),
        "new": 0,
        "matched": 0,
        "conflicts": 0,
        "businesses_created": 0,
        "businesses_merged": 0,
        "contacts_created": 0,
        "observations_created": 0,
        "memberships_created": 0,
        "conflict_examples": [],
    }
    niches = {row.slug: row for row in session.scalars(select(NicheModel))}
    observation_keys = {
        (row.business_id, row.source, row.content_hash): row.id
        for row in session.scalars(select(SourceObservationModel))
    }

    for position, record in enumerate(selected, start=1):
        disposition, target_id = index.resolve(record)
        summary[disposition if disposition != "conflict" else "conflicts"] += 1
        if disposition == "conflict":
            if len(summary["conflict_examples"]) < 20:
                summary["conflict_examples"].append(
                    {
                        "source_business_id": record["business"].get("id"),
                        "display_name": record["business"].get("display_name"),
                    }
                )
            continue
        if not apply:
            virtual_id = target_id or f"planned:{position}"
            index.add_business(
                virtual_id,
                record["business"],
                record.get("observations") or [],
            )
            continue

        if target_id:
            business = session.get(BusinessModel, target_id)
            if business is None:
                raise RuntimeError(f"matched target business disappeared: {target_id}")
            _merge_business(business, record["business"])
            summary["businesses_merged"] += 1
        else:
            business = _create_business(record["business"])
            session.add(business)
            session.flush()
            summary["businesses_created"] += 1

        summary["contacts_created"] += _merge_contacts(
            session, business.id, record.get("contacts") or []
        )
        observation_map, created = _merge_observations(
            session,
            business.id,
            record.get("observations") or [],
            observation_keys,
        )
        summary["observations_created"] += created
        summary["memberships_created"] += _merge_memberships(
            session,
            business.id,
            record.get("memberships") or [],
            observation_map,
            niches,
        )
        reconcile_business_facts(session, business.id)
        index.add_business(
            business.id,
            _business_payload(business),
            record.get("observations") or [],
        )
        if position % max(1, commit_every) == 0:
            session.commit()
    if apply:
        session.commit()
    else:
        session.rollback()
    return summary


def _create_business(data: dict[str, Any]) -> BusinessModel:
    now = utcnow()
    return BusinessModel(
        id=new_id("business"),
        display_name=data["display_name"],
        normalized_name=normalize_business_name(data["display_name"]),
        website_url=data.get("website_url"),
        domain=normalize_domain(data.get("domain") or data.get("website_url")),
        phone=normalize_phone(data.get("phone")),
        address=data.get("address"),
        geography=data.get("geography"),
        category_key=data.get("category_key"),
        market_key=data.get("market_key"),
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
        customer_kind=data.get("customer_kind") or "unknown",
        is_chain=data.get("is_chain"),
        is_franchise=data.get("is_franchise"),
        is_directory=data.get("is_directory"),
        is_agency=data.get("is_agency"),
        semantic_text=data.get("semantic_text"),
        status="active",
        first_seen_at=_dt(data.get("first_seen_at")) or now,
        last_seen_at=_dt(data.get("last_seen_at")) or now,
    )


def _merge_business(target: BusinessModel, source: dict[str, Any]) -> None:
    for field in (
        "website_url",
        "domain",
        "phone",
        "address",
        "geography",
        "category_key",
        "market_key",
        "latitude",
        "longitude",
        "semantic_text",
        "is_chain",
        "is_franchise",
        "is_directory",
        "is_agency",
    ):
        if getattr(target, field) in (None, "") and source.get(field) not in (None, ""):
            setattr(target, field, source[field])
    source_last_seen = _dt(source.get("last_seen_at"))
    if source_last_seen and source_last_seen > target.last_seen_at:
        target.last_seen_at = source_last_seen


def _merge_contacts(session: Session, business_id: str, rows: list[dict[str, Any]]) -> int:
    existing = list(
        session.scalars(select(ContactModel).where(ContactModel.business_id == business_id))
    )
    existing_emails = {
        email for row in existing if (email := normalize_email(row.email))
    }
    existing_phone_only = {
        phone
        for row in existing
        if not normalize_email(row.email) and (phone := normalize_phone(row.phone))
    }
    created = 0
    for data in rows:
        email = normalize_email(data.get("email"))
        phone = normalize_phone(data.get("phone"))
        if (
            (not email and not phone)
            or (email is not None and email in existing_emails)
            or (email is None and phone in existing_phone_only)
        ):
            continue
        session.add(
            ContactModel(
                id=new_id("contact"),
                business_id=business_id,
                name=data.get("name"),
                role=data.get("role"),
                email=email,
                phone=phone,
                verification_status=data.get("verification_status") or "unverified",
                verification_provider=data.get("verification_provider"),
                verification_checked_at=_dt(data.get("verification_checked_at")),
                verification_reason=data.get("verification_reason"),
                verification_score=data.get("verification_score"),
                verification_details=data.get("verification_details"),
                first_seen_at=_dt(data.get("first_seen_at")) or utcnow(),
                last_seen_at=_dt(data.get("last_seen_at")) or utcnow(),
            )
        )
        if email:
            existing_emails.add(email)
        elif phone:
            existing_phone_only.add(phone)
        created += 1
    session.flush()
    return created


def _merge_observations(
    session: Session,
    business_id: str,
    rows: list[dict[str, Any]],
    existing_keys: dict[tuple[str, str, str], str],
) -> tuple[dict[str, str], int]:
    id_map: dict[str, str] = {}
    created = 0
    for data in rows:
        key = (business_id, data["source"], data["content_hash"])
        observation_id = existing_keys.get(key)
        if observation_id is None:
            observation_id = new_id("sourceobs")
            session.add(
                SourceObservationModel(
                    id=observation_id,
                    business_id=business_id,
                    source=data["source"],
                    external_id=data.get("external_id"),
                    query_signature=data.get("query_signature"),
                    content_hash=data["content_hash"],
                    source_url=data.get("source_url"),
                    raw_payload=data.get("raw_payload") or {},
                    observed_at=_dt(data.get("observed_at")) or utcnow(),
                )
            )
            existing_keys[key] = observation_id
            created += 1
        id_map[data["id"]] = observation_id
    session.flush()
    return id_map, created


def _merge_memberships(
    session: Session,
    business_id: str,
    rows: list[dict[str, Any]],
    observation_map: dict[str, str],
    niches: dict[str, NicheModel],
) -> int:
    existing = {
        (row.niche_id, row.market_key): row
        for row in session.scalars(
            select(BusinessNicheMembershipModel).where(
                BusinessNicheMembershipModel.business_id == business_id
            )
        )
    }
    created = 0
    for data in rows:
        niche_data = data["niche"]
        niche = niches.get(niche_data["slug"])
        if niche is None:
            niche = NicheModel(
                id=new_id("niche"),
                slug=niche_data["slug"],
                label=niche_data["label"],
                category=niche_data.get("category"),
                default_query=niche_data.get("default_query"),
                active=bool(niche_data.get("active", True)),
                signal_vocabulary=niche_data.get("signal_vocabulary") or [],
            )
            session.add(niche)
            session.flush()
            niches[niche.slug] = niche
        key = (niche.id, data["market_key"])
        membership = existing.get(key)
        source_observation_id = observation_map.get(data.get("source_observation_id"))
        if membership is None:
            membership = BusinessNicheMembershipModel(
                id=new_id("bizniche"),
                business_id=business_id,
                niche_id=niche.id,
                market_key=data["market_key"],
                confidence=float(data.get("confidence") or 1.0),
                evidence=data.get("evidence") or [],
                source_observation_id=source_observation_id,
                seed_batch_id=None,
                first_seen_at=_dt(data.get("first_seen_at")) or utcnow(),
                last_seen_at=_dt(data.get("last_seen_at")) or utcnow(),
            )
            session.add(membership)
            existing[key] = membership
            created += 1
        else:
            membership.confidence = max(
                membership.confidence, float(data.get("confidence") or 0)
            )
            membership.source_observation_id = (
                membership.source_observation_id or source_observation_id
            )
            source_last_seen = _dt(data.get("last_seen_at"))
            if source_last_seen and source_last_seen > membership.last_seen_at:
                membership.last_seen_at = source_last_seen
    session.flush()
    return created


def _business_payload(row: BusinessModel) -> dict[str, Any]:
    return {
        field: getattr(row, field)
        for field in (
            "id",
            "display_name",
            "normalized_name",
            "website_url",
            "domain",
            "phone",
            "address",
            "geography",
            "category_key",
            "market_key",
            "latitude",
            "longitude",
            "customer_kind",
            "is_chain",
            "is_franchise",
            "is_directory",
            "is_agency",
            "semantic_text",
            "status",
            "first_seen_at",
            "last_seen_at",
        )
    }


def _contact_payload(row: ContactModel) -> dict[str, Any]:
    return {
        field: getattr(row, field)
        for field in (
            "name",
            "role",
            "email",
            "phone",
            "verification_status",
            "verification_provider",
            "verification_checked_at",
            "verification_reason",
            "verification_score",
            "verification_details",
            "first_seen_at",
            "last_seen_at",
        )
    }


def _observation_payload(row: SourceObservationModel) -> dict[str, Any]:
    return {
        field: getattr(row, field)
        for field in (
            "id",
            "source",
            "external_id",
            "query_signature",
            "content_hash",
            "source_url",
            "raw_payload",
            "observed_at",
        )
    }


def _membership_payload(
    row: BusinessNicheMembershipModel,
    niche: NicheModel,
) -> dict[str, Any]:
    return {
        "market_key": row.market_key,
        "confidence": row.confidence,
        "evidence": row.evidence,
        "source_observation_id": row.source_observation_id,
        "first_seen_at": row.first_seen_at,
        "last_seen_at": row.last_seen_at,
        "niche": {
            "slug": niche.slug,
            "label": niche.label,
            "category": niche.category,
            "default_query": niche.default_query,
            "active": niche.active,
            "signal_vocabulary": niche.signal_vocabulary,
        },
    }


def _group_by_business(rows) -> dict[str, list[Any]]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        grouped[row.business_id].append(row)
    return grouped


def _read_records(path: Path) -> list[dict[str, Any]]:
    records = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            record = json.loads(stripped)
            if record.get("version") != 1 or not isinstance(record.get("business"), dict):
                raise ValueError(f"invalid migration record at line {line_number}")
            records.append(record)
    return records


def _dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return None


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export")
    export.add_argument("--output", type=Path, required=True)
    for name in ("plan", "import"):
        command = commands.add_parser(name)
        command.add_argument("--input", type=Path, required=True)
        command.add_argument("--limit", type=int)
        command.add_argument("--commit-every", type=int, default=25)
        if name == "import":
            command.add_argument("--apply", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
