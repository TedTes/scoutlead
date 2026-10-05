"""reconcile canonical websites from trusted observations

Revision ID: 20261005_0034
Revises: 20261005_0033
Create Date: 2026-10-05
"""

from collections import defaultdict
from datetime import datetime, timezone
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

from canonical.normalization import normalize_domain
from canonical.website_evidence import trusted_website_evidence


revision = "20261005_0034"
down_revision = "20261005_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    required = {
        "businesses",
        "source_observations",
        "business_facts",
        "leads",
    }
    if not all(inspector.has_table(table) for table in required):
        return

    metadata = sa.MetaData()
    businesses = sa.Table("businesses", metadata, autoload_with=bind)
    observations = sa.Table("source_observations", metadata, autoload_with=bind)
    facts = sa.Table("business_facts", metadata, autoload_with=bind)
    leads = sa.Table("leads", metadata, autoload_with=bind)
    now = datetime.now(timezone.utc)

    observations_by_business: dict[str, list[dict]] = defaultdict(list)
    for row in bind.execute(
        sa.select(
            observations.c.id,
            observations.c.business_id,
            observations.c.source,
            observations.c.raw_payload,
            observations.c.observed_at,
        ).order_by(observations.c.observed_at.desc())
    ).mappings():
        observations_by_business[str(row["business_id"])].append(dict(row))

    website_facts = {
        str(row["business_id"]): dict(row)
        for row in bind.execute(
            sa.select(facts).where(facts.c.fact_key == "website_status")
        ).mappings()
    }
    for business in bind.execute(
        sa.select(
            businesses.c.id,
            businesses.c.display_name,
            businesses.c.phone,
            businesses.c.website_url,
        )
    ).mappings():
        business_id = str(business["id"])
        business_observations = observations_by_business.get(business_id, [])
        website_url = business["website_url"]
        evidence_observation = None
        if not website_url:
            for observation in business_observations:
                evidence = trusted_website_evidence(
                    source=str(observation["source"] or ""),
                    payload=observation["raw_payload"] or {},
                    business_name=str(business["display_name"] or ""),
                    business_phone=business["phone"],
                )
                if evidence is None:
                    continue
                website_url = evidence.url
                evidence_observation = observation
                break

        if website_url:
            bind.execute(
                businesses.update()
                .where(businesses.c.id == business_id)
                .values(
                    website_url=website_url,
                    domain=normalize_domain(website_url),
                    updated_at=now,
                )
            )
            bind.execute(
                leads.update()
                .where(
                    leads.c.business_id == business_id,
                    leads.c.website_url.is_(None),
                )
                .values(website_url=website_url, updated_at=now)
            )
            current = website_facts.get(business_id)
            current_value = current.get("value_text") if current else None
            website_status = (
                current_value
                if current_value in {"unavailable", "parked"}
                else "present"
            )
            _write_website_fact(
                bind,
                facts,
                current,
                business_id=business_id,
                value=website_status,
                confidence=100,
                source_observation_id=(
                    evidence_observation["id"] if evidence_observation else None
                ),
                now=now,
            )
            _synchronize_leads(
                bind,
                leads,
                business_id=business_id,
                website_url=website_url,
                website_status=website_status,
                now=now,
            )
            continue

        current = website_facts.get(business_id)
        if current is None or current.get("value_text") != "present":
            continue
        value, confidence, source_observation_id = _latest_absence(
            business_observations
        )
        _write_website_fact(
            bind,
            facts,
            current,
            business_id=business_id,
            value=value,
            confidence=confidence,
            source_observation_id=source_observation_id,
            now=now,
        )
        _synchronize_leads(
            bind,
            leads,
            business_id=business_id,
            website_url=None,
            website_status=value,
            now=now,
        )


def downgrade() -> None:
    # This migration repairs derived canonical data and is intentionally irreversible.
    pass


def _latest_absence(observations: list[dict]) -> tuple[str, int, str | None]:
    mapping = {
        "no_website_found": ("not_listed", 65),
        "no_website_listed": ("not_listed", 55),
        "unavailable": ("unavailable", 95),
        "website_unavailable": ("unavailable", 95),
        "parked": ("parked", 95),
        "website_parked": ("parked", 95),
    }
    for observation in observations:
        presence = (observation.get("raw_payload") or {}).get("website_presence")
        if not isinstance(presence, dict):
            continue
        result = mapping.get(str(presence.get("status") or "").strip().lower())
        if result is not None:
            return result[0], result[1], str(observation["id"])
    return "unknown", 0, None


def _write_website_fact(
    bind,
    facts,
    current: dict | None,
    *,
    business_id: str,
    value: str,
    confidence: int,
    source_observation_id: str | None,
    now: datetime,
) -> None:
    values = {
        "value_type": "text",
        "value_text": value,
        "value_number": None,
        "value_boolean": None,
        "confidence": confidence,
        "observed_at": now,
        "expires_at": None,
        "source_observation_id": source_observation_id,
        "resolver_version": 3,
        "updated_at": now,
    }
    if current is not None:
        bind.execute(
            facts.update().where(facts.c.id == current["id"]).values(**values)
        )
        return
    bind.execute(
        facts.insert().values(
            id=f"business_fact_{uuid4().hex}",
            business_id=business_id,
            fact_key="website_status",
            created_at=now,
            **values,
        )
    )


def _synchronize_leads(
    bind,
    leads,
    *,
    business_id: str,
    website_url: str | None,
    website_status: str,
    now: datetime,
) -> None:
    for lead in bind.execute(
        sa.select(leads.c.id, leads.c.website_url, leads.c.raw_sources).where(
            leads.c.business_id == business_id
        )
    ).mappings():
        raw_sources = lead["raw_sources"] or []
        raw_changed = _replace_website_fact(raw_sources, website_status)
        values = {"updated_at": now}
        if website_url and lead["website_url"] != website_url:
            values["website_url"] = website_url
        if raw_changed:
            values["raw_sources"] = raw_sources
        if len(values) > 1:
            bind.execute(
                leads.update().where(leads.c.id == lead["id"]).values(**values)
            )


def _replace_website_fact(value, website_status: str) -> bool:
    changed = False
    if isinstance(value, dict):
        facts = value.get("business_facts")
        if isinstance(facts, dict):
            current = facts.get("website_status")
            if isinstance(current, dict):
                if current.get("value") != website_status:
                    current["value"] = website_status
                    changed = True
            elif current != website_status:
                facts["website_status"] = website_status
                changed = True
        for entry in value.values():
            changed = _replace_website_fact(entry, website_status) or changed
    elif isinstance(value, list):
        for entry in value:
            changed = _replace_website_fact(entry, website_status) or changed
    return changed
