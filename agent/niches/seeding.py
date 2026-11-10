from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import NicheModel
from niches.catalog import search_config_for_slug
from shared.utils import new_id


ALLOWED_CATALOG_STATUSES = {"supported", "planned", "custom"}


@dataclass(frozen=True)
class TradeCatalogEntry:
    key: str
    label: str
    category: str
    aliases: tuple[str, ...]
    status: str


@dataclass
class TradeCatalogSeedSummary:
    catalog_entries: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    conflicts: int = 0
    supported: int = 0
    planned: int = 0
    dry_run: bool = False

    def to_dict(self) -> dict[str, int | bool]:
        return asdict(self)


def load_trade_catalog(path: Path) -> list[TradeCatalogEntry]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("trades"), list):
        raise ValueError("trade catalog must contain a trades array")
    entries: list[TradeCatalogEntry] = []
    seen: set[str] = set()
    for index, raw in enumerate(payload["trades"], start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"trade {index} must be an object")
        key = str(raw.get("key") or "").strip()
        label = str(raw.get("label") or "").strip()
        category = str(raw.get("category") or "").strip()
        status = str(raw.get("status") or "planned").strip().lower()
        aliases_raw = raw.get("aliases") or []
        if not key or not label or not category:
            raise ValueError(f"trade {index} requires key, label, and category")
        if key in seen:
            raise ValueError(f"duplicate trade key: {key}")
        if status not in ALLOWED_CATALOG_STATUSES:
            raise ValueError(f"unsupported status for {key}: {status}")
        if not isinstance(aliases_raw, list):
            raise ValueError(f"aliases for {key} must be an array")
        aliases = tuple(
            dict.fromkeys(
                value
                for value in (str(alias).strip() for alias in aliases_raw)
                if value
            )
        )
        entries.append(
            TradeCatalogEntry(
                key=key,
                label=label,
                category=category,
                aliases=aliases,
                status=status,
            )
        )
        seen.add(key)
    return entries


def seed_trade_catalog(
    session: Session,
    entries: list[TradeCatalogEntry],
    *,
    dry_run: bool = False,
) -> TradeCatalogSeedSummary:
    summary = TradeCatalogSeedSummary(
        catalog_entries=len(entries),
        supported=sum(entry.status == "supported" for entry in entries),
        planned=sum(entry.status == "planned" for entry in entries),
        dry_run=dry_run,
    )
    existing_by_slug = {
        niche.slug: niche for niche in session.scalars(select(NicheModel))
    }
    next_order = int(
        session.scalar(select(func.max(NicheModel.display_order))) or 0
    )

    for entry in entries:
        niche = existing_by_slug.get(entry.key)
        if niche is not None and niche.created_by_workspace_id is not None:
            # A workspace draft is not silently converted into shared taxonomy.
            summary.conflicts += 1
            continue

        if niche is None:
            next_order += 1
            niche = NicheModel(
                id=new_id("niche"),
                slug=entry.key,
                label=entry.label,
                category=entry.category,
                default_query=entry.label,
                active=entry.status == "supported",
                catalog_status=entry.status,
                display_order=next_order,
                created_by_workspace_id=None,
                search_config=_catalog_search_config(entry),
            )
            session.add(niche)
            existing_by_slug[entry.key] = niche
            summary.inserted += 1
            continue

        changes = _catalog_changes(niche, entry)
        if not changes:
            summary.unchanged += 1
            continue
        for field, value in changes.items():
            setattr(niche, field, value)
        summary.updated += 1

    if dry_run:
        session.rollback()
    else:
        session.commit()
    return summary


def _catalog_changes(
    niche: NicheModel,
    entry: TradeCatalogEntry,
) -> dict[str, Any]:
    expected: dict[str, Any] = {
        "label": entry.label,
        "category": entry.category,
        "catalog_status": entry.status,
        "search_config": {
            **(niche.search_config or {}),
            **_catalog_search_config(entry),
        },
    }
    if not niche.default_query:
        expected["default_query"] = entry.label
    if entry.status == "supported" and not niche.active:
        expected["active"] = True
    # Planned catalog entries never deactivate an already-used niche.
    return {
        field: value
        for field, value in expected.items()
        if getattr(niche, field) != value
    }


def _catalog_search_config(entry: TradeCatalogEntry) -> dict[str, Any]:
    configured = search_config_for_slug(entry.key)
    return {
        "aliases": list(entry.aliases),
        "include_terms": configured.get("include_terms", []),
        "exclude_terms": configured.get("exclude_terms", []),
        "catalog_status": entry.status,
    }
