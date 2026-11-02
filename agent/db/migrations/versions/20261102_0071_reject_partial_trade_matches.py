"""reject trade validations created from partial-word matches

Revision ID: 20261102_0071
Revises: 20261102_0070
Create Date: 2026-11-02

Older trade validation used substring checks, so ``paint`` classified
``Painted Post Convenience`` as a painting business. Reclassify those existing
validations; future validation uses complete words or phrases.
"""

from __future__ import annotations

import json
import re

from alembic import op
import sqlalchemy as sa


revision = "20261102_0071"
down_revision = "20261102_0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("validation_results") or not inspector.has_table(
        "source_items"
    ):
        return

    metadata = sa.MetaData()
    validations = sa.Table("validation_results", metadata, autoload_with=bind)
    items = sa.Table("source_items", metadata, autoload_with=bind)
    rows = bind.execute(
        sa.select(
            validations.c.id,
            validations.c.evidence,
            items.c.title,
            items.c.raw_payload,
        )
        .select_from(
            validations.join(items, validations.c.source_item_id == items.c.id)
        )
        .where(
            validations.c.validation_type == "trade",
            validations.c.status == "passed",
        )
    ).mappings()

    for row in rows:
        matched_terms = _matched_terms(row["evidence"])
        if not matched_terms:
            continue
        independent_text, structured_text = _independent_text(
            row["title"], row["raw_payload"]
        )
        exact_match = any(
            _contains_term(independent_text, term) for term in matched_terms
        )
        if exact_match:
            continue
        structured_conflict = bool(structured_text)
        values = {
            "status": "failed" if structured_conflict else "uncertain",
            "confidence": 95 if structured_conflict else 35,
            "reason": (
                "Structured provider categories do not support the requested trade."
                if structured_conflict
                else "Previous trade validation relied on a partial-word match."
            ),
        }
        if "validator_version" in validations.c.keys():
            values["validator_version"] = 6
        bind.execute(
            validations.update().where(validations.c.id == row["id"]).values(**values)
        )


def downgrade() -> None:
    # Restoring known false-positive validations would make unrelated entities
    # searchable again.
    pass


def _matched_terms(value) -> set[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return set()
    if not isinstance(value, list):
        return set()
    return {
        str(term).strip().lower()
        for item in value
        if isinstance(item, dict)
        for term in (item.get("matched_terms") or [])
        if str(term).strip()
    }


def _independent_text(title, payload) -> tuple[str, str]:
    raw = _payload(payload)
    merged = _nested_raw(raw)
    tags = merged.get("tags") if isinstance(merged.get("tags"), dict) else {}
    structured = [
        raw.get("category"),
        merged.get("primaryType"),
        merged.get("primaryTypeDisplayName"),
        *(merged.get("types") or []),
        *(merged.get("categories") or []),
        *(tags.get(key) for key in ("craft", "office", "shop", "amenity")),
    ]
    structured = [value for value in structured if value not in (None, "", [])]
    independent = [
        title,
        raw.get("snippet"),
        raw.get("description"),
        *structured,
    ]
    return _normalized(json.dumps(independent, default=str)), _normalized(
        json.dumps(structured, default=str)
    )


def _contains_term(text: str, term: str) -> bool:
    normalized_term = _normalized(term)
    return bool(
        normalized_term
        and re.search(
            rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])",
            text,
        )
    )


def _normalized(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def _nested_raw(payload: dict) -> dict:
    merged: dict = {}
    layers: list[dict] = []
    current = payload
    while isinstance(current, dict):
        layers.append(current)
        nested = current.get("raw")
        if not isinstance(nested, dict):
            break
        current = nested
    for layer in reversed(layers):
        merged.update(layer)
    return merged


def _payload(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}
