"""Tests for the Prometheus metrics definitions module.

Verifies that all metric objects are properly defined with the correct
type, label names, and (for histograms) custom bucket configurations.
Uses a snapshot+delta pattern for counters to avoid cross-test interference.
"""

from __future__ import annotations

from backend.common.metrics import (
    APP_INFO,
    CELERY_TASK_DURATION_SECONDS,
    CELERY_TASK_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_IN_PROGRESS,
    HTTP_REQUESTS_TOTAL,
    TRADES_EXECUTED_TOTAL,
    TRADES_RISK_BLOCKED_TOTAL,
    TRADING_CYCLES_TOTAL,
    WEATHER_FETCHES_TOTAL,
    set_app_info,
)

# ─── Helpers ───


def _counter_value(counter, labels: dict) -> float:
    """Get the current value of a Counter with the given labels."""
    return counter.labels(**labels)._value.get()


# ─── App Info ───


class TestAppInfo:
    def test_set_app_info_stores_values(self):
        """set_app_info() should populate the app_info metric."""
        set_app_info(version="1.2.3", environment="test")
        # Info metrics store a dict via .info()
        sample = APP_INFO.collect()[0].samples[0]
        assert sample.labels["version"] == "1.2.3"
        assert sample.labels["environment"] == "test"

    def test_set_app_info_includes_both_labels(self):
        """Both version and environment should be present in the metric."""
        set_app_info(version="0.1.0", environment="production")
        sample = APP_INFO.collect()[0].samples[0]
        assert "version" in sample.labels
        assert "environment" in sample.labels


# ─── HTTP Metric Definitions ───


class TestHTTPMetricDefinitions:
    def test_http_requests_total_accepts_labels(self):
        """Counter should accept method, path_template, status_code labels."""
        before = _counter_value(
            HTTP_REQUESTS_TOTAL,
            {"method": "GET", "path_template": "/test", "status_code": "200"},
        )
        HTTP_REQUESTS_TOTAL.labels(method="GET", path_template="/test", status_code="200").inc()
        after = _counter_value(
            HTTP_REQUESTS_TOTAL,
            {"method": "GET", "path_template": "/test", "status_code": "200"},
        )
        assert after - before == 1.0

    def test_http_request_duration_accepts_labels(self):
        """Histogram should accept method, path_template labels."""
        # Should not raise
        HTTP_REQUEST_DURATION_SECONDS.labels(method="POST", path_template="/api/trades").observe(
            0.05
        )

    def test_http_requests_in_progress_accepts_labels(self):
        """Gauge should accept method label."""
        HTTP_REQUESTS_IN_PROGRESS.labels(method="GET").inc()
        HTTP_REQUESTS_IN_PROGRESS.labels(method="GET").dec()
        # Should not raise

    def test_http_duration_has_custom_buckets(self):
        """Verify histogram buckets are tuned for HTTP latency (5ms–10s)."""
        # The _upper_bounds include all explicit buckets + Inf
        buckets = HTTP_REQUEST_DURATION_SECONDS._kwargs["buckets"]
        assert buckets[0] == 0.005  # 5ms
        assert buckets[-1] == 10.0  # 10s
        assert len(buckets) == 11


# ─── Celery Metric Definitions ───


class TestCeleryMetricDefinitions:
    def test_celery_task_total_accepts_labels(self):
        """Counter should accept task_name, status labels."""
        before = _counter_value(
            CELERY_TASK_TOTAL,
            {"task_name": "test_task", "status": "success"},
        )
        CELERY_TASK_TOTAL.labels(task_name="test_task", status="success").inc()
        after = _counter_value(
            CELERY_TASK_TOTAL,
            {"task_name": "test_task", "status": "success"},
        )
        assert after - before == 1.0

    def test_celery_task_duration_has_custom_buckets(self):
        """Verify histogram buckets are tuned for Celery tasks (0.1s–300s)."""
        buckets = CELERY_TASK_DURATION_SECONDS._kwargs["buckets"]
        assert buckets[0] == 0.1
        assert buckets[-1] == 300.0


# ─── Business Metric Definitions ───


class TestBusinessMetricDefinitions:
    def test_trading_cycles_total_accepts_outcome_label(self):
        """Counter should accept outcome label."""
        before = _counter_value(TRADING_CYCLES_TOTAL, {"outcome": "test_completed"})
        TRADING_CYCLES_TOTAL.labels(outcome="test_completed").inc()
        after = _counter_value(TRADING_CYCLES_TOTAL, {"outcome": "test_completed"})
        assert after - before == 1.0

    def test_trades_executed_total_accepts_mode_and_city(self):
        """Counter should accept mode and city labels."""
        before = _counter_value(TRADES_EXECUTED_TOTAL, {"mode": "auto", "city": "TEST"})
        TRADES_EXECUTED_TOTAL.labels(mode="auto", city="TEST").inc()
        after = _counter_value(TRADES_EXECUTED_TOTAL, {"mode": "auto", "city": "TEST"})
        assert after - before == 1.0

    def test_trades_risk_blocked_total_accepts_reason(self):
        """Counter should accept reason label."""
        before = _counter_value(TRADES_RISK_BLOCKED_TOTAL, {"reason": "test_limit"})
        TRADES_RISK_BLOCKED_TOTAL.labels(reason="test_limit").inc()
        after = _counter_value(TRADES_RISK_BLOCKED_TOTAL, {"reason": "test_limit"})
        assert after - before == 1.0

    def test_weather_fetches_total_accepts_labels(self):
        """Counter should accept source, city, outcome labels."""
        before = _counter_value(
            WEATHER_FETCHES_TOTAL,
            {"source": "NWS", "city": "TEST", "outcome": "success"},
        )
        WEATHER_FETCHES_TOTAL.labels(source="NWS", city="TEST", outcome="success").inc()
        after = _counter_value(
            WEATHER_FETCHES_TOTAL,
            {"source": "NWS", "city": "TEST", "outcome": "success"},
        )
        assert after - before == 1.0
