"""Tests for the accuracy API endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.common.models import CityEnum, Prediction, Settlement, WeatherForecast

pytestmark = pytest.mark.asyncio


# ─── Helpers ───


def _make_forecast(
    city: str = "NYC",
    source: str = "NWS",
    forecast_date: datetime | None = None,
    forecast_high_f: float = 55.0,
) -> WeatherForecast:
    """Create a WeatherForecast ORM model."""
    return WeatherForecast(
        city=CityEnum(city),
        source=source,
        forecast_date=forecast_date or datetime(2026, 2, 10, tzinfo=UTC),
        forecast_high_f=forecast_high_f,
        fetched_at=datetime.now(UTC),
    )


def _make_settlement(
    city: str = "NYC",
    settlement_date: datetime | None = None,
    actual_high_f: float = 56.0,
) -> Settlement:
    """Create a Settlement ORM model."""
    return Settlement(
        city=CityEnum(city),
        settlement_date=settlement_date or datetime(2026, 2, 10, tzinfo=UTC),
        actual_high_f=actual_high_f,
        source="NWS_CLI",
    )


def _make_prediction(
    city: str = "NYC",
    prediction_date: datetime | None = None,
    brackets: list[dict] | None = None,
) -> Prediction:
    """Create a Prediction ORM model with 6 test brackets."""
    default_brackets = [
        {"bracket_label": "≤52°F", "lower_bound_f": None, "upper_bound_f": 52, "probability": 0.08},
        {"bracket_label": "53-54°F", "lower_bound_f": 53, "upper_bound_f": 54, "probability": 0.15},
        {"bracket_label": "55-56°F", "lower_bound_f": 55, "upper_bound_f": 56, "probability": 0.30},
        {"bracket_label": "57-58°F", "lower_bound_f": 57, "upper_bound_f": 58, "probability": 0.28},
        {"bracket_label": "59-60°F", "lower_bound_f": 59, "upper_bound_f": 60, "probability": 0.12},
        {"bracket_label": "≥61°F", "lower_bound_f": 61, "upper_bound_f": None, "probability": 0.07},
    ]
    return Prediction(
        city=CityEnum(city),
        prediction_date=prediction_date or datetime(2026, 2, 10, tzinfo=UTC),
        brackets_json=brackets or default_brackets,
        ensemble_mean_f=56.3,
        ensemble_std_f=2.1,
        confidence="medium",
        model_sources="NWS,GFS,ECMWF,ICON",
        generated_at=datetime.now(UTC),
    )


# ─── /api/accuracy/sources Tests ───


class TestGetAccuracySources:
    """Tests for GET /api/accuracy/sources."""

    async def test_empty_data(self, client: AsyncClient) -> None:
        """No forecast/settlement data → empty list."""
        response = await client.get("/api/accuracy/sources?city=NYC")
        assert response.status_code == 200
        assert response.json() == []

    async def test_with_forecast_and_settlement(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        """Returns source accuracy when matching data exists."""
        dt = datetime(2026, 2, 10, tzinfo=UTC)
        fc = _make_forecast(city="NYC", source="NWS", forecast_date=dt, forecast_high_f=55.0)
        st = _make_settlement(city="NYC", settlement_date=dt, actual_high_f=57.0)
        db.add(fc)
        db.add(st)
        await db.flush()

        response = await client.get("/api/accuracy/sources?city=NYC")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        nws = next((s for s in data if s["source"] == "NWS"), None)
        assert nws is not None
        assert nws["sample_count"] == 1

    async def test_city_parameter(self, client: AsyncClient) -> None:
        """City parameter is accepted."""
        for city in ("NYC", "CHI", "MIA", "AUS"):
            response = await client.get(f"/api/accuracy/sources?city={city}")
            assert response.status_code == 200

    async def test_lookback_days_parameter(self, client: AsyncClient) -> None:
        """Custom lookback_days is accepted."""
        response = await client.get("/api/accuracy/sources?city=NYC&lookback_days=30")
        assert response.status_code == 200

    async def test_lookback_days_validation(self, client: AsyncClient) -> None:
        """lookback_days must be between 1 and 365."""
        response = await client.get("/api/accuracy/sources?lookback_days=0")
        assert response.status_code == 422

        response = await client.get("/api/accuracy/sources?lookback_days=400")
        assert response.status_code == 422

    async def test_unauthenticated(self, unauthed_client: AsyncClient) -> None:
        """Returns 401 when not authenticated."""
        response = await unauthed_client.get("/api/accuracy/sources")
        assert response.status_code == 401


# ─── /api/accuracy/calibration Tests ───


class TestGetCalibration:
    """Tests for GET /api/accuracy/calibration."""

    async def test_insufficient_data(self, client: AsyncClient) -> None:
        """No data → insufficient_data status."""
        response = await client.get("/api/accuracy/calibration?city=NYC")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "insufficient_data"
        assert data["city"] == "NYC"
        assert data["brier_score"] is None

    async def test_with_sufficient_data(self, client: AsyncClient, db: AsyncSession) -> None:
        """Returns calibration report when enough data exists."""
        # Add 10 prediction+settlement pairs
        for i in range(10):
            dt = datetime(2026, 1, i + 1, tzinfo=UTC)
            pred = _make_prediction(city="NYC", prediction_date=dt)
            settle = _make_settlement(city="NYC", settlement_date=dt, actual_high_f=55.5)
            db.add(pred)
            db.add(settle)
        await db.flush()

        response = await client.get("/api/accuracy/calibration?city=NYC")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["sample_count"] == 10
        assert data["brier_score"] is not None
        assert len(data["calibration_buckets"]) > 0

    async def test_city_parameter(self, client: AsyncClient) -> None:
        """City parameter is echoed back in response."""
        response = await client.get("/api/accuracy/calibration?city=CHI")
        assert response.status_code == 200
        assert response.json()["city"] == "CHI"

    async def test_lookback_days_parameter(self, client: AsyncClient) -> None:
        """Custom lookback_days is accepted and echoed."""
        response = await client.get("/api/accuracy/calibration?city=NYC&lookback_days=60")
        assert response.status_code == 200
        assert response.json()["lookback_days"] == 60

    async def test_unauthenticated(self, unauthed_client: AsyncClient) -> None:
        """Returns 401 when not authenticated."""
        response = await unauthed_client.get("/api/accuracy/calibration")
        assert response.status_code == 401


# ─── /api/accuracy/trends Tests ───


class TestGetAccuracyTrends:
    """Tests for GET /api/accuracy/trends."""

    async def test_empty_data(self, client: AsyncClient) -> None:
        """No data → empty points, None rolling MAE."""
        response = await client.get("/api/accuracy/trends?city=NYC&source=NWS")
        assert response.status_code == 200
        data = response.json()
        assert data["city"] == "NYC"
        assert data["source"] == "NWS"
        assert data["points"] == []
        assert data["rolling_mae"] is None

    async def test_with_data(self, client: AsyncClient, db: AsyncSession) -> None:
        """Returns trend data when matching forecast/settlement exists."""
        dt = datetime(2026, 2, 10, tzinfo=UTC)
        fc = _make_forecast(city="NYC", source="NWS", forecast_date=dt, forecast_high_f=55.0)
        st = _make_settlement(city="NYC", settlement_date=dt, actual_high_f=57.0)
        db.add(fc)
        db.add(st)
        await db.flush()

        response = await client.get("/api/accuracy/trends?city=NYC&source=NWS")
        assert response.status_code == 200
        data = response.json()
        assert len(data["points"]) >= 1
        assert data["rolling_mae"] is not None

    async def test_source_parameter(self, client: AsyncClient) -> None:
        """Custom source parameter is echoed back."""
        response = await client.get("/api/accuracy/trends?city=NYC&source=Open-Meteo:GFS")
        assert response.status_code == 200
        assert response.json()["source"] == "Open-Meteo:GFS"

    async def test_default_parameters(self, client: AsyncClient) -> None:
        """Default parameters work without explicit query string."""
        response = await client.get("/api/accuracy/trends")
        assert response.status_code == 200
        data = response.json()
        assert data["city"] == "NYC"
        assert data["source"] == "NWS"

    async def test_lookback_days_validation(self, client: AsyncClient) -> None:
        """lookback_days must be between 1 and 365."""
        response = await client.get("/api/accuracy/trends?lookback_days=0")
        assert response.status_code == 422

    async def test_unauthenticated(self, unauthed_client: AsyncClient) -> None:
        """Returns 401 when not authenticated."""
        response = await unauthed_client.get("/api/accuracy/trends")
        assert response.status_code == 401
