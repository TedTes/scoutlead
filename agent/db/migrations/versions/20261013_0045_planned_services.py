"""add planned service definitions

Revision ID: 20261013_0045
Revises: 20261013_0044
Create Date: 2026-10-13
"""

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "20261013_0045"
down_revision = "20261013_0044"
branch_labels = None
depends_on = None


PLANNED_SERVICES = (
    (
        "service_crm_follow_up",
        "crm_follow_up_automation",
        "CRM and follow-up automation",
        "Missed responses, inconsistent follow-up, or manual lead handling.",
        80,
    ),
    (
        "service_social_media",
        "social_media_management",
        "Social media management",
        "Inactive profiles, inconsistent publishing, or weak social engagement.",
        90,
    ),
    (
        "service_branding_creative",
        "branding_creative",
        "Branding and creative services",
        "Outdated or inconsistent branding across public customer touchpoints.",
        100,
    ),
    (
        "service_recruiting_brand",
        "recruiting_employer_branding",
        "Recruiting and employer branding",
        "Active hiring with weak recruiting pages or employer positioning.",
        110,
    ),
    (
        "service_maintenance_plans",
        "maintenance_plan_consulting",
        "Maintenance-plan consulting",
        "No visible recurring service or customer-retention offering.",
        120,
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(
            sa.text(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = current_database()
                  AND pid <> pg_backend_pid()
                  AND state <> 'idle'
                  AND xact_start < now() - interval '2 minutes'
                  AND query ~* '(profile_delivery_items|territory_deliveries)'
                """
            )
        )
    now = datetime.now(timezone.utc)
    services = sa.table(
        "service_definitions",
        sa.column("id", sa.String),
        sa.column("key", sa.String),
        sa.column("label", sa.String),
        sa.column("description", sa.Text),
        sa.column("status", sa.String),
        sa.column("sort_order", sa.Integer),
        sa.column("version", sa.Integer),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        services,
        [
            {
                "id": service_id,
                "key": key,
                "label": label,
                "description": description,
                "status": "draft",
                "sort_order": sort_order,
                "version": 1,
                "created_at": now,
                "updated_at": now,
            }
            for service_id, key, label, description, sort_order in PLANNED_SERVICES
        ],
    )


def downgrade() -> None:
    service_ids = [service[0] for service in PLANNED_SERVICES]
    op.execute(
        sa.text("DELETE FROM service_definitions WHERE id IN :ids").bindparams(
            sa.bindparam("ids", expanding=True, value=service_ids)
        )
    )
