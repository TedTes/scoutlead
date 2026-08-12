"""initial schema

Revision ID: 20260812_0001
Revises:
Create Date: 2026-08-12
"""
from alembic import op

from db.base import Base
import db.models  # noqa: F401

revision = "20260812_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
