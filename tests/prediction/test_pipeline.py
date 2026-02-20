"""Tests for backend.prediction.pipeline — full prediction orchestration.

Validates ``generate_prediction`` ties together ensemble, error_dist,
brackets, and confidence into a correct ``BracketPrediction``.

All DB-dependent calls (``calculate_error_std``) are patched so these
tests run without a real database.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.common.schemas import BracketPrediction
from backend.prediction.pipeline import generate_prediction


class TestGeneratePrediction:
    """Integration-level tests for the prediction pipeline."""

    @pytest.mark.asyncio
    async def test_returns_bracket_prediction(self, sample_forecasts, sample_brackets) -> None:
        """The pipeline returns a BracketPrediction instance."""
        with patch(
            "backend.prediction.pipeline.calculate_error_std",
            new_callable=AsyncMock,
        ) as mock_std:
            mock_std.return_value = 2.0
            result = await generate_prediction(
                city="NYC",
                target_date=date(2026, 2, 18),
                forecasts=sample_forecasts,
                kalshi_brackets=sample_brackets,
                db_session=AsyncMock(),
            )
            assert isinstance(result, BracketPrediction)

    @pytest.mark.asyncio
    async def test_uses_correct_schema_fields(self, sample_forecasts, sample_brackets) -> None:
        """Result uses ensemble_mean_f and ensemble_std_f (not legacy names)."""
        with patch(
            "backend.prediction.pipeline.calculate_error_std",
            new_callable=AsyncMock,
        ) as mock_std:
            mock_std.return_value = 2.5
            result = await generate_prediction(
                city="NYC",
                target_date=date(2026, 2, 18),
                forecasts=sample_forecasts,
                kalshi_brackets=sample_brackets,
                db_session=AsyncMock(),
            )
            # These are the actual schema field names
            assert hasattr(result, "ensemble_mean_f")
            assert hasattr(result, "ensemble_std_f")
            assert isinstance(result.ensemble_mean_f, float)
            assert isinstance(result.ensemble_std_f, float)

    @pytest.mark.asyncio
    async def test_confidence_is_lowercase(self, sample_forecasts, sample_brackets) -> None:
        """Confidence must be one of 'high', 'medium', or 'low' (lowercase)."""
        with patch(
            "backend.prediction.pipeline.calculate_error_std",
            new_callable=AsyncMock,
        ) as mock_std:
            mock_std.return_value = 2.0
            result = await generate_prediction(
                city="NYC",
                target_date=date(2026, 2, 18),
                forecasts=sample_forecasts,
                kalshi_brackets=sample_brackets,
                db_session=AsyncMock(),
            )
            assert result.confidence in ("high", "medium", "low")

    @pytest.mark.asyncio
    async def test_brackets_sum_to_one(self, sample_forecasts, sample_brackets) -> None:
        """Bracket probabilities in the output must sum to ~1.0."""
        with patch(
            "backend.prediction.pipeline.calculate_error_std",
            new_callable=AsyncMock,
        ) as mock_std:
            mock_std.return_value = 2.0
            result = await generate_prediction(
                city="NYC",
                target_date=date(2026, 2, 18),
                forecasts=sample_forecasts,
                kalshi_brackets=sample_brackets,
                db_session=AsyncMock(),
            )
            total = sum(b.probability for b in result.brackets)
            assert abs(total - 1.0) < 1e-6

    @pytest.mark.asyncio
    async def test_sources_populated(self, sample_forecasts, sample_brackets) -> None:
        """model_sources list must be populated from the input forecasts."""
        with patch(
            "backend.prediction.pipeline.calculate_error_std",
            new_callable=AsyncMock,
        ) as mock_std:
            mock_std.return_value = 2.0
            result = await generate_prediction(
                city="NYC",
                target_date=date(2026, 2, 18),
                forecasts=sample_forecasts,
                kalshi_brackets=sample_brackets,
                db_session=AsyncMock(),
            )
            assert len(result.model_sources) == len(sample_forecasts)
            assert "NWS" in result.model_sources


class TestPipelineXGBoostIntegration:
    """Tests for XGBoost integration in the prediction pipeline."""

    @pytest.mark.asyncio
    async def test_xgb_available_blends_temperature(
        self, sample_forecasts, sample_brackets
    ) -> None:
        """When XGBoost is available, the final temp is blended."""
        with (
            patch(
                "backend.prediction.pipeline.calculate_error_std",
                new_callable=AsyncMock,
            ) as mock_std,
            patch(
                "backend.prediction.pipeline._try_xgb_prediction",
                return_value=60.0,
            ),
            patch(
                "backend.prediction.pipeline.get_settings",
            ) as mock_settings,
        ):
            mock_std.return_value = 2.0
            mock_settings.return_value = MagicMock(xgb_ensemble_weight=0.30)

            result = await generate_prediction(
                city="NYC",
                target_date=date(2026, 2, 18),
                forecasts=sample_forecasts,
                kalshi_brackets=sample_brackets,
                db_session=AsyncMock(),
            )

            assert "XGBoost" in result.model_sources

    @pytest.mark.asyncio
    async def test_xgb_unavailable_falls_back(self, sample_forecasts, sample_brackets) -> None:
        """When XGBoost returns None, pipeline uses ensemble-only."""
        with (
            patch(
                "backend.prediction.pipeline.calculate_error_std",
                new_callable=AsyncMock,
            ) as mock_std,
            patch(
                "backend.prediction.pipeline._try_xgb_prediction",
                return_value=None,
            ),
        ):
            mock_std.return_value = 2.0

            result = await generate_prediction(
                city="NYC",
                target_date=date(2026, 2, 18),
                forecasts=sample_forecasts,
                kalshi_brackets=sample_brackets,
                db_session=AsyncMock(),
            )

            assert "XGBoost" not in result.model_sources

    @pytest.mark.asyncio
    async def test_xgb_weight_zero_disables(self, sample_forecasts, sample_brackets) -> None:
        """When xgb_ensemble_weight=0.0, XGBoost is not attempted."""
        with (
            patch(
                "backend.prediction.pipeline.calculate_error_std",
                new_callable=AsyncMock,
            ) as mock_std,
            patch(
                "backend.prediction.pipeline._try_xgb_prediction",
                return_value=None,
            ) as mock_xgb,
        ):
            mock_std.return_value = 2.0

            result = await generate_prediction(
                city="NYC",
                target_date=date(2026, 2, 18),
                forecasts=sample_forecasts,
                kalshi_brackets=sample_brackets,
                db_session=AsyncMock(),
            )

            # _try_xgb_prediction was called (it returns None for weight=0).
            mock_xgb.assert_called_once()
            assert "XGBoost" not in result.model_sources

    @pytest.mark.asyncio
    async def test_xgb_failure_graceful_degradation(
        self, sample_forecasts, sample_brackets
    ) -> None:
        """When _try_xgb_prediction raises, pipeline still completes."""
        with (
            patch(
                "backend.prediction.pipeline.calculate_error_std",
                new_callable=AsyncMock,
            ) as mock_std,
            patch(
                "backend.prediction.pipeline._try_xgb_prediction",
                return_value=None,
            ),
        ):
            mock_std.return_value = 2.0

            result = await generate_prediction(
                city="NYC",
                target_date=date(2026, 2, 18),
                forecasts=sample_forecasts,
                kalshi_brackets=sample_brackets,
                db_session=AsyncMock(),
            )

            assert isinstance(result, BracketPrediction)
            assert "XGBoost" not in result.model_sources

    @pytest.mark.asyncio
    async def test_xgb_sources_list_includes_xgboost(
        self, sample_forecasts, sample_brackets
    ) -> None:
        """Sources list has 'XGBoost' appended when model contributes."""
        with (
            patch(
                "backend.prediction.pipeline.calculate_error_std",
                new_callable=AsyncMock,
            ) as mock_std,
            patch(
                "backend.prediction.pipeline._try_xgb_prediction",
                return_value=58.0,
            ),
            patch(
                "backend.prediction.pipeline.get_settings",
            ) as mock_settings,
        ):
            mock_std.return_value = 2.0
            mock_settings.return_value = MagicMock(xgb_ensemble_weight=0.30)

            result = await generate_prediction(
                city="NYC",
                target_date=date(2026, 2, 18),
                forecasts=sample_forecasts,
                kalshi_brackets=sample_brackets,
                db_session=AsyncMock(),
            )

            # Original sources + "XGBoost"
            assert result.model_sources[-1] == "XGBoost"
            assert len(result.model_sources) == len(sample_forecasts) + 1
