"""Add Kelly Criterion position sizing columns to users table.

Adds four new columns for configuring Kelly Criterion bet sizing:
- use_kelly_sizing: Enable/disable Kelly sizing (default False)
- kelly_fraction: Fractional Kelly multiplier (default 0.25)
- max_bankroll_pct_per_trade: Max bankroll % per trade (default 0.05)
- max_contracts_per_trade: Hard cap on contracts (default 10)

Revision ID: 0004
Revises: 0003
Create Date: 2026-02-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add Kelly Criterion columns with safe defaults."""
    op.add_column(
        "users",
        sa.Column(
            "use_kelly_sizing",
            sa.Boolean(),
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "kelly_fraction",
            sa.Float(),
            server_default=sa.text("0.25"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "max_bankroll_pct_per_trade",
            sa.Float(),
            server_default=sa.text("0.05"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "max_contracts_per_trade",
            sa.Integer(),
            server_default=sa.text("10"),
        ),
    )


def downgrade() -> None:
    """Remove Kelly Criterion columns."""
    op.drop_column("users", "use_kelly_sizing")
    op.drop_column("users", "kelly_fraction")
    op.drop_column("users", "max_bankroll_pct_per_trade")
    op.drop_column("users", "max_contracts_per_trade")
