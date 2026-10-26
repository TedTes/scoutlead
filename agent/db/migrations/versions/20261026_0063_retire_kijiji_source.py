"""retire Kijiji as a source and remove its evidence

Revision ID: 20261026_0063
Revises: 20261025_0062
Create Date: 2026-10-26

This cleanup deliberately preserves user workflow records. Businesses supported
only by Kijiji are archived; businesses with independent observations remain
active after the Kijiji evidence and derived rows are removed.
"""

from alembic import op
import sqlalchemy as sa


revision = "20261026_0063"
down_revision = "20261025_0062"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _run(statement: str) -> None:
    op.get_bind().execute(sa.text(statement))


def _remove_retired_claim_references() -> None:
    """Remove deleted Kijiji claim IDs without changing unrelated fact quality."""
    bind = op.get_bind()
    metadata = sa.MetaData()
    facts = sa.Table("business_facts", metadata, autoload_with=bind)
    claims = sa.Table("fact_claims", metadata, autoload_with=bind)
    retired_claim_ids = set(
        bind.execute(
            sa.select(claims.c.id).where(
                claims.c.source_observation_id.in_(
                    sa.text("SELECT observation_id FROM retired_kijiji_observations")
                )
            )
        ).scalars()
    )
    if not retired_claim_ids:
        return
    rows = bind.execute(
        sa.select(facts.c.id, facts.c.supporting_claim_ids)
    ).all()
    for fact_id, supporting_claim_ids in rows:
        current = list(supporting_claim_ids or [])
        retained = [claim_id for claim_id in current if claim_id not in retired_claim_ids]
        if retained != current:
            bind.execute(
                facts.update()
                .where(facts.c.id == fact_id)
                .values(supporting_claim_ids=retained)
            )


def upgrade() -> None:
    if not _has_table("businesses"):
        return

    _run(
        """
        CREATE TEMPORARY TABLE IF NOT EXISTS retired_kijiji_observations (
            observation_id VARCHAR(64) PRIMARY KEY,
            business_id VARCHAR(64) NOT NULL
        )
        """
    )
    _run("DELETE FROM retired_kijiji_observations")
    if _has_table("source_observations"):
        _run(
            """
            INSERT INTO retired_kijiji_observations (observation_id, business_id)
            SELECT id, business_id
            FROM source_observations
            WHERE LOWER(source) LIKE '%kijiji%'
            """
        )

    _run(
        """
        CREATE TEMPORARY TABLE IF NOT EXISTS retired_kijiji_only_businesses (
            business_id VARCHAR(64) PRIMARY KEY
        )
        """
    )
    _run("DELETE FROM retired_kijiji_only_businesses")
    if _has_table("source_observations"):
        _run(
            """
            INSERT INTO retired_kijiji_only_businesses (business_id)
            SELECT DISTINCT retired.business_id
            FROM retired_kijiji_observations AS retired
            WHERE NOT EXISTS (
                SELECT 1
                FROM source_observations AS independent
                WHERE independent.business_id = retired.business_id
                  AND LOWER(independent.source) NOT LIKE '%kijiji%'
            )
            """
        )

    _run(
        """
        CREATE TEMPORARY TABLE IF NOT EXISTS retired_kijiji_website_businesses (
            business_id VARCHAR(64) PRIMARY KEY
        )
        """
    )
    _run("DELETE FROM retired_kijiji_website_businesses")
    _run(
        """
        INSERT INTO retired_kijiji_website_businesses (business_id)
        SELECT id
        FROM businesses
        WHERE LOWER(COALESCE(website_url, '')) LIKE '%kijiji.%'
           OR LOWER(COALESCE(domain, '')) LIKE '%kijiji.%'
        """
    )

    if _has_table("business_niche_memberships"):
        _run(
            """
            DELETE FROM business_niche_memberships
            WHERE source_observation_id IN (
                SELECT observation_id FROM retired_kijiji_observations
            )
            OR seed_batch_id IN (
                SELECT id FROM seed_batches WHERE LOWER(source) LIKE '%kijiji%'
            )
            """
            if _has_table("seed_batches")
            else """
            DELETE FROM business_niche_memberships
            WHERE source_observation_id IN (
                SELECT observation_id FROM retired_kijiji_observations
            )
            """
        )
        _run(
            """
            DELETE FROM business_niche_memberships
            WHERE business_id IN (
                SELECT business_id FROM retired_kijiji_only_businesses
            )
            """
        )
    if _has_table("business_facts"):
        _run(
            """
            DELETE FROM business_facts
            WHERE source_observation_id IN (
                SELECT observation_id FROM retired_kijiji_observations
            )
            OR (
                business_id IN (
                    SELECT business_id FROM retired_kijiji_website_businesses
                )
                AND fact_key IN (
                    'website_status',
                    'contact_form_present',
                    'quote_or_booking_form_present'
                )
            )
            """
        )
        _run(
            """
            DELETE FROM business_facts
            WHERE business_id IN (
                SELECT business_id FROM retired_kijiji_only_businesses
            )
            """
        )
    if _has_table("business_fact_changes"):
        _run(
            """
            DELETE FROM business_fact_changes
            WHERE source_observation_id IN (
                SELECT observation_id FROM retired_kijiji_observations
            )
            """
        )
    if _has_table("fact_claims"):
        if _has_table("business_facts"):
            _remove_retired_claim_references()
        _run(
            """
            DELETE FROM fact_claims
            WHERE source_observation_id IN (
                SELECT observation_id FROM retired_kijiji_observations
            )
            """
        )
    if _has_table("validation_results"):
        _run(
            """
            DELETE FROM validation_results
            WHERE source_observation_id IN (
                SELECT observation_id FROM retired_kijiji_observations
            )
            """
        )
        _run(
            """
            DELETE FROM validation_results
            WHERE business_id IN (
                SELECT business_id FROM retired_kijiji_only_businesses
            )
            """
        )

    # Remove unreviewed discovery output backed only by the retired source, while
    # retaining explicit shortlist/contact/dismiss history as an audit trail.
    if _has_table("audience_results"):
        _run(
            """
            DELETE FROM audience_results
            WHERE business_id IN (
                SELECT business_id FROM retired_kijiji_only_businesses
            )
              AND review_status = 'unreviewed'
              AND reviewed_at IS NULL
              AND shortlisted_at IS NULL
              AND contacted_at IS NULL
            """
        )

    if _has_table("source_items"):
        if _has_table("validation_results"):
            _run(
                """
                DELETE FROM validation_results
                WHERE source_item_id IN (
                    SELECT id FROM source_items
                    WHERE LOWER(provider_id) LIKE '%kijiji%'
                )
                """
            )
        if _has_table("source_item_decisions"):
            _run(
                """
                DELETE FROM source_item_decisions
                WHERE source_item_id IN (
                    SELECT id FROM source_items
                    WHERE LOWER(provider_id) LIKE '%kijiji%'
                )
                """
            )
        _run("DELETE FROM source_items WHERE LOWER(provider_id) LIKE '%kijiji%'")

    if _has_table("source_observations"):
        _run(
            """
            DELETE FROM source_observations
            WHERE id IN (SELECT observation_id FROM retired_kijiji_observations)
            """
        )
    if _has_table("campaign_sources"):
        _run("DELETE FROM campaign_sources WHERE LOWER(provider_id) LIKE '%kijiji%'")
    if _has_table("seed_batches"):
        _run(
            """
            UPDATE seed_batches
            SET status = 'retired'
            WHERE LOWER(source) LIKE '%kijiji%'
            """
        )

    _run(
        """
        UPDATE businesses
        SET website_url = NULL, domain = NULL
        WHERE id IN (SELECT business_id FROM retired_kijiji_website_businesses)
        """
    )
    _run(
        """
        UPDATE businesses
        SET status = 'archived'
        WHERE id IN (SELECT business_id FROM retired_kijiji_only_businesses)
        """
    )


def downgrade() -> None:
    # Removed third-party evidence cannot be reconstructed safely.
    pass
