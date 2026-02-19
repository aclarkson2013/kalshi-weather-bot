"""Add demo_mode column to users table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-02-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add demo_mode boolean column with default True (safe default)."""
    op.add_column(
        "users",
        sa.Column("demo_mode", sa.Boolean(), server_default=sa.text("true")),
    )


def downgrade() -> None:
    """Remove demo_mode column."""
    op.drop_column("users", "demo_mode")
