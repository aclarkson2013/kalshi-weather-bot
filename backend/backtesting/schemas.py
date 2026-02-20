"""Pydantic schemas for backtesting configuration and results.

All monetary values are in CENTS (int), consistent with the rest of the project.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.common.schemas import CityCode, ConfidenceLevel, TradeSide

# ─── Configuration ───


class BacktestConfig(BaseModel):
    """Configuration for a backtest run."""

    cities: list[CityCode] = ["NYC", "CHI", "MIA", "AUS"]
    start_date: date
    end_date: date
    initial_bankroll_cents: int = Field(default=100_000, ge=1_000)  # $10 min
    min_ev_threshold: float = Field(default=0.02, ge=0.0, le=1.0)
    use_kelly: bool = True
    kelly_fraction: float = Field(default=0.25, ge=0.01, le=1.0)
    max_daily_trades: int = Field(default=20, ge=1, le=100)
    consecutive_loss_limit: int = Field(default=5, ge=1, le=50)
    max_contracts_per_trade: int = Field(default=10, ge=1, le=100)
    max_bankroll_pct_per_trade: float = Field(default=0.05, ge=0.01, le=0.25)
    price_noise_cents: int = Field(default=5, ge=0, le=20)

    @model_validator(mode="after")
    def validate_date_range(self) -> BacktestConfig:
        """Ensure end_date >= start_date."""
        if self.end_date < self.start_date:
            msg = f"end_date ({self.end_date}) must be >= start_date ({self.start_date})"
            raise ValueError(msg)
        return self

    @field_validator("cities")
    @classmethod
    def validate_cities(cls, v: list[CityCode]) -> list[CityCode]:
        """Ensure at least one city is selected."""
        if not v:
            msg = "At least one city must be selected"
            raise ValueError(msg)
        return v


# ─── Simulated Trade ───


class SimulatedTrade(BaseModel):
    """A single simulated trade from the backtest."""

    day: date
    city: CityCode
    bracket_label: str
    side: TradeSide
    price_cents: int = Field(ge=1, le=99)
    quantity: int = Field(ge=1)
    model_probability: float = Field(ge=0.0, le=1.0)
    market_probability: float = Field(ge=0.0, le=1.0)
    ev: float
    confidence: ConfidenceLevel
    actual_temp_f: float
    won: bool
    pnl_cents: int
    fees_cents: int
    bankroll_after_cents: int


# ─── Per-Day Results ───


class BacktestDay(BaseModel):
    """Results for a single simulated day."""

    day: date
    trades: list[SimulatedTrade] = []
    daily_pnl_cents: int = 0
    bankroll_start_cents: int = 0
    bankroll_end_cents: int = 0
    trades_blocked_by_risk: int = 0


# ─── Per-City Stats ───


class CityStats(BaseModel):
    """Aggregated stats for one city."""

    city: CityCode
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    total_pnl_cents: int = 0
    avg_ev: float = 0.0


# ─── Kelly Effectiveness Stats ───


class KellyStats(BaseModel):
    """Statistics about Kelly sizing effectiveness."""

    avg_quantity: float = 0.0
    max_quantity: int = 0
    pnl_vs_flat: int = 0  # PnL improvement over flat 1-contract sizing (cents)
    avg_edge_cents: float = 0.0


# ─── Full Backtest Result ───


class BacktestResult(BaseModel):
    """Complete result of a backtest run."""

    config: BacktestConfig
    days: list[BacktestDay] = []
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    total_pnl_cents: int = 0
    roi_pct: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    per_city_stats: dict[str, CityStats] = {}
    kelly_stats: KellyStats | None = None
    duration_seconds: float = 0.0
    total_days_simulated: int = 0
    days_with_trades: int = 0
