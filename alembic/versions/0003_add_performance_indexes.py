"""Add performance indexes for trading queries.

Adds composite indexes that optimize the most frequent queries:
- Trade lookups by user + status (risk manager exposure check)
- Trade lookups by user + trade_date (daily P&L)
- Settlement lookups by city + date (settlement pipeline)
- Prediction lookups by city + generated_at (latest prediction per city)

Revision ID: 0003
Revises: 0002
Create Date: 2026-02-20
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add composite indexes for common query patterns."""
    # Risk manager: get_open_exposure_cents() — WHERE user_id=X AND status='OPEN'
    op.create_index(
        "ix_trade_user_status",
        "trades",
        ["user_id", "status"],
    )

    # Risk manager: get_daily_pnl_cents() — WHERE user_id=X AND trade_date=Y
    op.create_index(
        "ix_trade_user_date",
        "trades",
        ["user_id", "trade_date"],
    )

    # Prediction pipeline: latest prediction per city
    op.create_index(
        "ix_prediction_city_generated",
        "predictions",
        ["city", "generated_at"],
    )


def downgrade() -> None:
    """Remove performance indexes."""
    op.drop_index("ix_trade_user_status", table_name="trades")
    op.drop_index("ix_trade_user_date", table_name="trades")
    op.drop_index("ix_prediction_city_generated", table_name="predictions")
