"""Tests for backend.prediction.calibration — Brier score + calibration buckets."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.prediction.calibration import _temp_in_bracket, check_calibration

# ─── Helpers ───


def _mock_session_with_rows(rows: list) -> AsyncMock:
    """Create a mock DB session returning the given rows from execute()."""
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = rows
    session.execute.return_value = mock_result
    return session


def _make_brackets(probs: list[float]) -> list[dict]:
    """Create 6 bracket definitions with given probabilities.

    Brackets: <=52, 53-54, 55-56, 57-58, 59-60, >=61
    """
    labels = [
        {"bracket_label": "≤52°F", "lower_bound_f": None, "upper_bound_f": 52},
        {"bracket_label": "53-54°F", "lower_bound_f": 53, "upper_bound_f": 54},
        {"bracket_label": "55-56°F", "lower_bound_f": 55, "upper_bound_f": 56},
        {"bracket_label": "57-58°F", "lower_bound_f": 57, "upper_bound_f": 58},
        {"bracket_label": "59-60°F", "lower_bound_f": 59, "upper_bound_f": 60},
        {"bracket_label": "≥61°F", "lower_bound_f": 61, "upper_bound_f": None},
    ]
    for i, label in enumerate(labels):
        label["probability"] = probs[i]
    return labels


# ─── _temp_in_bracket Tests ───


class TestTempInBracket:
    """Tests for the bracket matching helper."""

    def test_bottom_catchall(self) -> None:
        """Bottom bracket (None, 52) includes temps <= 52."""
        assert _temp_in_bracket(50.0, None, 52.0) is True
        assert _temp_in_bracket(52.0, None, 52.0) is True
        assert _temp_in_bracket(53.0, None, 52.0) is False

    def test_top_catchall(self) -> None:
        """Top bracket (61, None) includes temps >= 61."""
        assert _temp_in_bracket(61.0, 61.0, None) is True
        assert _temp_in_bracket(65.0, 61.0, None) is True
        assert _temp_in_bracket(60.0, 61.0, None) is False

    def test_middle_bracket(self) -> None:
        """Middle brackets are [lower, upper) — lower-inclusive, upper-exclusive."""
        assert _temp_in_bracket(55.0, 55.0, 56.0) is True
        assert _temp_in_bracket(55.5, 55.0, 56.0) is True
        assert _temp_in_bracket(56.0, 55.0, 56.0) is False

    def test_both_none(self) -> None:
        """If both bounds are None, any temp matches."""
        assert _temp_in_bracket(99.0, None, None) is True


# ─── check_calibration Tests ───


@pytest.mark.asyncio
class TestCheckCalibration:
    """Tests for the calibration computation."""

    async def test_insufficient_data(self) -> None:
        """Fewer than 10 rows → status='insufficient_data', no Brier score."""
        rows = [(_make_brackets([0.1, 0.2, 0.3, 0.2, 0.1, 0.1]), 55.0)] * 5
        session = _mock_session_with_rows(rows)
        result = await check_calibration("NYC", session)
        assert result.status == "insufficient_data"
        assert result.sample_count == 5
        assert result.brier_score is None
        assert result.calibration_buckets == []

    async def test_exactly_at_threshold(self) -> None:
        """Exactly 10 rows → status='ok'."""
        brackets = _make_brackets([0.1, 0.2, 0.3, 0.2, 0.1, 0.1])
        rows = [(brackets, 55.5)] * 10
        session = _mock_session_with_rows(rows)
        result = await check_calibration("NYC", session)
        assert result.status == "ok"
        assert result.sample_count == 10
        assert result.brier_score is not None

    async def test_perfect_predictions(self) -> None:
        """When predictions are 1.0 for the correct bracket, Brier = 0.0."""
        # Every day: predict 100% for 55-56, actual = 55.5 (lands in 55-56)
        brackets = _make_brackets([0.0, 0.0, 1.0, 0.0, 0.0, 0.0])
        rows = [(brackets, 55.5)] * 10
        session = _mock_session_with_rows(rows)
        result = await check_calibration("NYC", session)
        assert result.status == "ok"
        assert result.brier_score == 0.0

    async def test_worst_predictions(self) -> None:
        """When predictions are 1.0 for the wrong bracket → high Brier score."""
        # Predict 100% for >=61, but actual = 50.0 (lands in <=52)
        brackets = _make_brackets([0.0, 0.0, 0.0, 0.0, 0.0, 1.0])
        rows = [(brackets, 50.0)] * 10
        session = _mock_session_with_rows(rows)
        result = await check_calibration("NYC", session)
        assert result.status == "ok"
        # Brier: each day has 6 brackets, >=61 bracket: (1-0)^2 = 1.0, <=52: (0-1)^2 = 1.0
        # Other 4 brackets: (0-0)^2 = 0.0 each
        # Total per day: 2.0, over 6 brackets → per-bracket: 2.0
        # 10 days × 6 brackets = 60 predictions, sum = 20.0
        # Brier = 20.0 / 60 = 0.3333
        assert result.brier_score is not None
        assert result.brier_score == pytest.approx(0.3333, abs=0.001)

    async def test_brier_score_calculation(self) -> None:
        """Verify Brier score with manually calculated expected value."""
        # Uniform prediction: each bracket gets 1/6 ≈ 0.1667
        prob = 1.0 / 6.0
        brackets = _make_brackets([prob] * 6)
        # Actual temp = 55.5 → lands in bracket [55, 56)
        rows = [(brackets, 55.5)] * 10
        session = _mock_session_with_rows(rows)
        result = await check_calibration("NYC", session)
        # Per day: one bracket has outcome=1, five have outcome=0
        # Hit bracket: (1/6 - 1)^2 = (5/6)^2 ≈ 0.6944
        # Miss brackets: (1/6 - 0)^2 = (1/6)^2 ≈ 0.0278 each × 5 = 0.1389
        # Day total: 0.6944 + 0.1389 = 0.8333
        # Brier = 0.8333 / 6 ≈ 0.1389
        expected_brier = ((5 / 6) ** 2 + 5 * (1 / 6) ** 2) / 6
        assert result.brier_score == pytest.approx(expected_brier, abs=0.001)

    async def test_calibration_buckets_present(self) -> None:
        """Calibration buckets are returned for bins with data."""
        brackets = _make_brackets([0.05, 0.15, 0.35, 0.25, 0.12, 0.08])
        rows = [(brackets, 55.5)] * 10
        session = _mock_session_with_rows(rows)
        result = await check_calibration("NYC", session)
        assert len(result.calibration_buckets) > 0
        # Each bucket should have valid bin range
        for bucket in result.calibration_buckets:
            assert 0.0 <= bucket.bin_start < bucket.bin_end <= 1.0
            assert bucket.sample_count > 0

    async def test_calibration_bucket_bins(self) -> None:
        """Verify that predictions are binned correctly by probability."""
        # 5% → bin [0.0, 0.1), 15% → bin [0.1, 0.2), 30% → bin [0.3, 0.4)
        brackets = _make_brackets([0.05, 0.15, 0.30, 0.25, 0.15, 0.10])
        rows = [(brackets, 55.5)] * 10
        session = _mock_session_with_rows(rows)
        result = await check_calibration("NYC", session)
        bin_starts = [b.bin_start for b in result.calibration_buckets]
        assert 0.0 in bin_starts  # 0.05 prediction
        assert 0.1 in bin_starts  # 0.10, 0.15 predictions
        assert 0.2 in bin_starts  # 0.25 prediction
        assert 0.3 in bin_starts  # 0.30 prediction

    async def test_city_echoed_back(self) -> None:
        """Result includes the requested city."""
        for city in ("NYC", "CHI", "MIA", "AUS"):
            session = _mock_session_with_rows([])
            result = await check_calibration(city, session)
            assert result.city == city

    async def test_lookback_days_echoed_back(self) -> None:
        """Result includes the requested lookback_days."""
        session = _mock_session_with_rows([])
        result = await check_calibration("NYC", session, lookback_days=30)
        assert result.lookback_days == 30

    async def test_json_string_brackets(self) -> None:
        """Brackets stored as JSON string (not native Python list) are parsed."""
        import json

        brackets = _make_brackets([0.0, 0.0, 1.0, 0.0, 0.0, 0.0])
        rows = [(json.dumps(brackets), 55.5)] * 10
        session = _mock_session_with_rows(rows)
        result = await check_calibration("NYC", session)
        assert result.status == "ok"
        assert result.brier_score == 0.0

    async def test_actual_in_bottom_bracket(self) -> None:
        """Actual temp in the bottom catch-all bracket."""
        brackets = _make_brackets([0.5, 0.1, 0.1, 0.1, 0.1, 0.1])
        rows = [(brackets, 50.0)] * 10  # 50°F ≤ 52°F → bottom bracket
        session = _mock_session_with_rows(rows)
        result = await check_calibration("NYC", session)
        assert result.status == "ok"
        assert result.brier_score is not None

    async def test_actual_in_top_bracket(self) -> None:
        """Actual temp in the top catch-all bracket."""
        brackets = _make_brackets([0.1, 0.1, 0.1, 0.1, 0.1, 0.5])
        rows = [(brackets, 65.0)] * 10  # 65°F ≥ 61°F → top bracket
        session = _mock_session_with_rows(rows)
        result = await check_calibration("NYC", session)
        assert result.status == "ok"
        assert result.brier_score is not None

    async def test_returns_calibration_report_type(self) -> None:
        """Return type is CalibrationReport Pydantic model."""
        from backend.api.response_schemas import CalibrationReport

        session = _mock_session_with_rows([])
        result = await check_calibration("NYC", session)
        assert isinstance(result, CalibrationReport)
