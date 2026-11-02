from importlib import import_module

import sqlalchemy as sa


migration = import_module(
    "db.migrations.versions.20261102_0071_reject_partial_trade_matches"
)


def test_migration_rejects_partial_trade_word_with_conflicting_provider_type(
    monkeypatch,
) -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    items = sa.Table(
        "source_items",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("title", sa.String),
        sa.Column("raw_payload", sa.JSON, nullable=False),
    )
    validations = sa.Table(
        "validation_results",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("source_item_id", sa.String, nullable=False),
        sa.Column("validation_type", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("confidence", sa.Integer, nullable=False),
        sa.Column("reason", sa.String, nullable=False),
        sa.Column("evidence", sa.JSON, nullable=False),
        sa.Column("validator_version", sa.Integer, nullable=False),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            items.insert(),
            [
                {
                    "id": "partial",
                    "title": "Painted Post Convenience",
                    "raw_payload": {"raw": {"types": ["convenience_store"]}},
                },
                {
                    "id": "exact",
                    "title": "Neighbourhood Painting",
                    "raw_payload": {"raw": {"types": ["painter"]}},
                },
            ],
        )
        connection.execute(
            validations.insert(),
            [
                {
                    "id": "partial_validation",
                    "source_item_id": "partial",
                    "validation_type": "trade",
                    "status": "passed",
                    "confidence": 95,
                    "reason": "old substring match",
                    "evidence": [{"matched_terms": ["paint"]}],
                    "validator_version": 5,
                },
                {
                    "id": "exact_validation",
                    "source_item_id": "exact",
                    "validation_type": "trade",
                    "status": "passed",
                    "confidence": 95,
                    "reason": "valid exact match",
                    "evidence": [{"matched_terms": ["painting"]}],
                    "validator_version": 5,
                },
            ],
        )
        monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
        migration.upgrade()
        rows = {
            row.id: row
            for row in connection.execute(
                sa.select(
                    validations.c.id,
                    validations.c.status,
                    validations.c.confidence,
                    validations.c.validator_version,
                )
            )
        }

    assert rows["partial_validation"].status == "failed"
    assert rows["partial_validation"].confidence == 95
    assert rows["partial_validation"].validator_version == 6
    assert rows["exact_validation"].status == "passed"
