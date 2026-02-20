"""API response and request schemas -- types used only by the REST layer."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from backend.common.schemas import (
    BracketPrediction,
    CityCode,
    TradeRecord,
)


class AuthValidateRequest(BaseModel):
    """Request body for validating Kalshi API credentials."""

    key_id: str
    private_key: str
    demo_mode: bool = True  # Default to demo for safety


class AuthValidateResponse(BaseModel):
    """Response after successfully validating Kalshi API credentials."""

    valid: bool
    balance_cents: int
    demo_mode: bool


class AuthStatusResponse(BaseModel):
    """Response for checking current authentication status."""

    authenticated: bool
    user_id: str
    demo_mode: bool
    key_id_prefix: str


class DashboardData(BaseModel):
    """Aggregated dashboard data for the frontend."""

    balance_cents: int
    today_pnl_cents: int
    active_positions: list[TradeRecord]
    recent_trades: list[TradeRecord]
    next_market_launch: str | None
    predictions: list[BracketPrediction]


class TradesPage(BaseModel):
    """Paginated trade history response."""

    trades: list[TradeRecord]
    total: int
    page: int


class LogEntryResponse(BaseModel):
    """A single structured log entry for the log viewer."""

    id: int
    timestamp: datetime
    level: str
    module: str
    message: str
    data: dict | None = None


class CumulativePnlPoint(BaseModel):
    """A single point on the cumulative P&L chart."""

    date: str
    cumulative_pnl: int


class AccuracyPoint(BaseModel):
    """A single point on the accuracy-over-time chart."""

    date: str
    accuracy: float


class PerformanceData(BaseModel):
    """Aggregated performance metrics for the analytics dashboard."""

    total_trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl_cents: int
    best_trade_pnl_cents: int
    worst_trade_pnl_cents: int
    cumulative_pnl: list[CumulativePnlPoint]
    pnl_by_city: dict[str, int]
    accuracy_over_time: list[AccuracyPoint]


class CalibrationBucket(BaseModel):
    """A single calibration bucket — predicted probability bin vs actual outcome rate."""

    bin_start: float
    bin_end: float
    predicted_avg: float
    actual_rate: float
    sample_count: int


class CalibrationReport(BaseModel):
    """Calibration report for a city's bracket predictions."""

    city: str
    lookback_days: int
    sample_count: int
    brier_score: float | None
    calibration_buckets: list[CalibrationBucket]
    status: str  # "ok" or "insufficient_data"


class SourceAccuracy(BaseModel):
    """Per-source forecast accuracy metrics (forecast vs settlement)."""

    source: str
    sample_count: int
    mae_f: float
    rmse_f: float
    bias_f: float


class ForecastErrorPoint(BaseModel):
    """A single point on the forecast error trend line."""

    date: str
    error_f: float


class ForecastErrorTrend(BaseModel):
    """Time series of forecast errors for a source/city combination."""

    city: str
    source: str
    points: list[ForecastErrorPoint]
    rolling_mae: float | None


class AccuracyOverview(BaseModel):
    """Combined accuracy overview — sources + calibration."""

    sources: list[SourceAccuracy]
    calibration: CalibrationReport


class SettingsUpdate(BaseModel):
    """Partial update for user settings -- all fields optional."""

    trading_mode: Literal["auto", "manual"] | None = None
    max_trade_size_cents: int | None = None
    daily_loss_limit_cents: int | None = None
    max_daily_exposure_cents: int | None = None
    min_ev_threshold: float | None = None
    cooldown_per_loss_minutes: int | None = None
    consecutive_loss_limit: int | None = None
    active_cities: list[CityCode] | None = None
    notifications_enabled: bool | None = None
    demo_mode: bool | None = None
