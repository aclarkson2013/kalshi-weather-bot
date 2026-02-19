"""Initial schema — all 8 tables.

Revision ID: 0001
Revises: None
Create Date: 2026-02-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── users ──
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("kalshi_key_id", sa.String(), nullable=False),
        sa.Column("encrypted_private_key", sa.Text(), nullable=False),
        sa.Column("trading_mode", sa.String(), server_default="manual"),
        sa.Column("max_trade_size_cents", sa.Integer(), server_default="100"),
        sa.Column("daily_loss_limit_cents", sa.Integer(), server_default="1000"),
        sa.Column("max_daily_exposure_cents", sa.Integer(), server_default="2500"),
        sa.Column("min_ev_threshold", sa.Float(), server_default="0.05"),
        sa.Column("cooldown_per_loss_minutes", sa.Integer(), server_default="60"),
        sa.Column("consecutive_loss_limit", sa.Integer(), server_default="3"),
        sa.Column("active_cities", sa.String(), server_default="NYC,CHI,MIA,AUS"),
        sa.Column(
            "notifications_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
        ),
        sa.Column("push_subscription", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
        ),
    )

    # ── weather_forecasts ──
    op.create_table(
        "weather_forecasts",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("city", sa.String(), nullable=False),
        sa.Column("forecast_date", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("forecast_high_f", sa.Float(), nullable=False),
        sa.Column("forecast_low_f", sa.Float(), nullable=True),
        sa.Column("humidity_pct", sa.Float(), nullable=True),
        sa.Column("wind_speed_mph", sa.Float(), nullable=True),
        sa.Column("cloud_cover_pct", sa.Float(), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_forecast_city_date", "weather_forecasts", ["city", "forecast_date"])
    op.create_index("ix_forecast_source", "weather_forecasts", ["source"])

    # ── predictions ──
    op.create_table(
        "predictions",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("city", sa.String(), nullable=False),
        sa.Column("prediction_date", sa.DateTime(), nullable=False),
        sa.Column("ensemble_mean_f", sa.Float(), nullable=False),
        sa.Column("ensemble_std_f", sa.Float(), nullable=False),
        sa.Column("confidence", sa.String(), nullable=False),
        sa.Column("model_sources", sa.String(), nullable=False),
        sa.Column("brackets_json", sa.JSON(), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_prediction_city_date", "predictions", ["city", "prediction_date"])

    # ── trades ──
    op.create_table(
        "trades",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kalshi_order_id", sa.String(), nullable=True),
        sa.Column("city", sa.String(), nullable=False),
        sa.Column("trade_date", sa.DateTime(), nullable=False),
        sa.Column("market_ticker", sa.String(), nullable=False),
        sa.Column("bracket_label", sa.String(), nullable=False),
        sa.Column("side", sa.String(), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("model_probability", sa.Float(), nullable=False),
        sa.Column("market_probability", sa.Float(), nullable=False),
        sa.Column("ev_at_entry", sa.Float(), nullable=False),
        sa.Column("confidence", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default="OPEN"),
        sa.Column("settlement_temp_f", sa.Float(), nullable=True),
        sa.Column("settlement_source", sa.String(), nullable=True),
        sa.Column("pnl_cents", sa.Integer(), nullable=True),
        sa.Column("fees_cents", sa.Integer(), nullable=True),
        sa.Column("postmortem_narrative", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
        ),
        sa.Column("settled_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_trade_city_date", "trades", ["city", "trade_date"])
    op.create_index("ix_trade_status", "trades", ["status"])
    op.create_index("ix_trade_user", "trades", ["user_id"])

    # ── pending_trades ──
    op.create_table(
        "pending_trades",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("city", sa.String(), nullable=False),
        sa.Column("bracket_label", sa.String(), nullable=False),
        sa.Column("market_ticker", sa.String(), nullable=False),
        sa.Column("side", sa.String(), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("model_probability", sa.Float(), nullable=False),
        sa.Column("market_probability", sa.Float(), nullable=False),
        sa.Column("ev", sa.Float(), nullable=False),
        sa.Column("confidence", sa.String(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), server_default="PENDING"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("acted_at", sa.DateTime(), nullable=True),
    )

    # ── settlements ──
    op.create_table(
        "settlements",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("city", sa.String(), nullable=False),
        sa.Column("settlement_date", sa.DateTime(), nullable=False),
        sa.Column("actual_high_f", sa.Float(), nullable=False),
        sa.Column("actual_low_f", sa.Float(), nullable=True),
        sa.Column("source", sa.String(), server_default="NWS_CLI"),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_settlement_city_date", "settlements", ["city", "settlement_date"])

    # ── daily_risk_states ──
    op.create_table(
        "daily_risk_states",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("trading_day", sa.DateTime(), nullable=False),
        sa.Column("total_loss_cents", sa.Integer(), server_default="0"),
        sa.Column("total_exposure_cents", sa.Integer(), server_default="0"),
        sa.Column("consecutive_losses", sa.Integer(), server_default="0"),
        sa.Column("cooldown_until", sa.DateTime(), nullable=True),
        sa.Column("trades_count", sa.Integer(), server_default="0"),
    )
    op.create_index(
        "ix_risk_user_day",
        "daily_risk_states",
        ["user_id", "trading_day"],
        unique=True,
    )

    # ── log_entries ──
    op.create_table(
        "log_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column(
            "timestamp",
            sa.DateTime(),
            server_default=sa.text("now()"),
        ),
        sa.Column("level", sa.String(), nullable=False),
        sa.Column("module_tag", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=True),
    )
    op.create_index("ix_log_entries_timestamp", "log_entries", ["timestamp"])
    op.create_index("ix_log_entries_module_tag", "log_entries", ["module_tag"])


def downgrade() -> None:
    op.drop_table("log_entries")
    op.drop_table("daily_risk_states")
    op.drop_table("settlements")
    op.drop_table("pending_trades")
    op.drop_table("trades")
    op.drop_table("predictions")
    op.drop_table("weather_forecasts")
    op.drop_table("users")
