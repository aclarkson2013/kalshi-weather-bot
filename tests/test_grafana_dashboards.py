"""Validation tests for Grafana dashboard JSON files.

Ensures all provisioned dashboards are well-formed, reference real
Prometheus metrics, and have no structural issues that would prevent
Grafana from loading them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ─── Constants ───

DASHBOARDS_DIR = Path(__file__).resolve().parent.parent / "monitoring" / "grafana" / "dashboards"

# Metric names defined in backend/common/metrics.py — PromQL queries must
# reference at least one of these (with optional suffixes like _total, _bucket).
KNOWN_METRICS = {
    "app_info",
    "http_requests_total",
    "http_request_duration_seconds",
    "http_requests_in_progress",
    "celery_task_total",
    "celery_task_duration_seconds",
    "trading_cycles_total",
    "trades_executed_total",
    "trades_risk_blocked_total",
    "trading_cycle_step_duration_seconds",
    "trading_cycle_total_duration_seconds",
    "ws_connections_active",
    "ws_messages_sent_total",
    "ws_events_received_total",
    "kalshi_ws_connected",
    "kalshi_ws_messages_total",
    "kalshi_ws_reconnects_total",
    "kalshi_ws_cache_hits_total",
    "weather_fetches_total",
}

# Prometheus automatically generates these suffixes for histograms
HISTOGRAM_SUFFIXES = {"_bucket", "_count", "_sum"}

REQUIRED_TOP_LEVEL_FIELDS = {"uid", "title", "panels", "version"}
REQUIRED_PANEL_FIELDS = {"id", "title", "type", "gridPos"}


# ─── Helpers ───


def load_dashboard(path: Path) -> dict:
    """Load and parse a dashboard JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def collect_dashboard_files() -> list[Path]:
    """Return all .json files in the dashboards directory."""
    return sorted(DASHBOARDS_DIR.glob("*.json"))


def extract_promql_exprs(dashboard: dict) -> list[str]:
    """Extract all PromQL expressions from dashboard targets."""
    exprs = []
    for panel in dashboard.get("panels", []):
        for target in panel.get("targets", []):
            expr = target.get("expr", "")
            if expr:
                exprs.append(expr)
    return exprs


def metric_name_in_expr(metric: str, expr: str) -> bool:
    """Check if a metric name (with optional suffixes) appears in a PromQL expression."""
    if metric in expr:
        return True
    return any(f"{metric}{suffix}" in expr for suffix in HISTOGRAM_SUFFIXES)


# ─── Fixtures ───


@pytest.fixture
def dashboard_files() -> list[Path]:
    """Return all dashboard JSON file paths."""
    return collect_dashboard_files()


@pytest.fixture(params=collect_dashboard_files(), ids=lambda p: p.stem)
def dashboard_path(request: pytest.FixtureRequest) -> Path:
    """Parametrize tests over each dashboard file."""
    return request.param


@pytest.fixture
def dashboard(dashboard_path: Path) -> dict:
    """Load a single dashboard as a dict."""
    return load_dashboard(dashboard_path)


# ─── Tests ───


class TestDashboardDiscovery:
    """Verify dashboard files exist and are discoverable."""

    def test_dashboards_directory_exists(self) -> None:
        """The monitoring/grafana/dashboards/ directory exists."""
        assert DASHBOARDS_DIR.is_dir(), f"Missing dashboards dir: {DASHBOARDS_DIR}"

    def test_at_least_two_dashboards_exist(self, dashboard_files: list[Path]) -> None:
        """At least two dashboard JSON files are provisioned."""
        assert len(dashboard_files) >= 2, f"Expected >= 2 dashboards, found {len(dashboard_files)}"


class TestDashboardStructure:
    """Validate individual dashboard JSON structure."""

    def test_valid_json(self, dashboard_path: Path) -> None:
        """Dashboard file is valid JSON."""
        text = dashboard_path.read_text(encoding="utf-8")
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            pytest.fail(f"{dashboard_path.name}: Invalid JSON — {exc}")

    def test_has_required_top_level_fields(self, dashboard: dict) -> None:
        """Dashboard has uid, title, panels, and version."""
        missing = REQUIRED_TOP_LEVEL_FIELDS - set(dashboard.keys())
        assert not missing, f"Missing top-level fields: {missing}"

    def test_uid_is_non_empty_string(self, dashboard: dict) -> None:
        """Dashboard UID is a non-empty string."""
        uid = dashboard.get("uid")
        assert isinstance(uid, str) and len(uid) > 0, f"Invalid UID: {uid!r}"

    def test_panels_is_non_empty_list(self, dashboard: dict) -> None:
        """Dashboard has at least one panel."""
        panels = dashboard.get("panels", [])
        assert isinstance(panels, list) and len(panels) > 0, "No panels found"


class TestPanelStructure:
    """Validate individual panel configurations."""

    def test_panels_have_required_fields(self, dashboard: dict) -> None:
        """Every panel has id, title, type, and gridPos."""
        for panel in dashboard.get("panels", []):
            missing = REQUIRED_PANEL_FIELDS - set(panel.keys())
            assert not missing, f"Panel '{panel.get('title', '?')}' missing fields: {missing}"

    def test_no_duplicate_panel_ids(self, dashboard: dict) -> None:
        """Panel IDs are unique within a dashboard."""
        ids = [p["id"] for p in dashboard.get("panels", []) if "id" in p]
        duplicates = [pid for pid in ids if ids.count(pid) > 1]
        assert not duplicates, f"Duplicate panel IDs: {set(duplicates)}"

    def test_panels_have_valid_grid_positions(self, dashboard: dict) -> None:
        """Every panel gridPos has h, w, x, y as non-negative integers."""
        for panel in dashboard.get("panels", []):
            gp = panel.get("gridPos", {})
            for key in ("h", "w", "x", "y"):
                value = gp.get(key)
                assert isinstance(value, int) and value >= 0, (
                    f"Panel '{panel.get('title', '?')}' gridPos.{key} = {value!r}"
                )

    def test_panels_have_targets_with_expr(self, dashboard: dict) -> None:
        """Every panel has at least one target with a non-empty expr."""
        for panel in dashboard.get("panels", []):
            targets = panel.get("targets", [])
            assert len(targets) > 0, f"Panel '{panel.get('title', '?')}' has no targets"
            for target in targets:
                expr = target.get("expr", "")
                assert isinstance(expr, str) and len(expr) > 0, (
                    f"Panel '{panel.get('title', '?')}' has empty expr"
                )


class TestPromQLReferencesMetrics:
    """Verify PromQL expressions reference real metrics from metrics.py."""

    def test_every_expr_references_known_metric(self, dashboard: dict) -> None:
        """Each PromQL expression references at least one known metric name."""
        for panel in dashboard.get("panels", []):
            for target in panel.get("targets", []):
                expr = target.get("expr", "")
                if not expr:
                    continue
                found = any(metric_name_in_expr(m, expr) for m in KNOWN_METRICS)
                assert found, (
                    f"Panel '{panel.get('title', '?')}' expr references no known metric: {expr}"
                )


class TestDashboardUniqueness:
    """Cross-dashboard validation — UIDs and titles must be unique."""

    def test_dashboard_uids_are_unique(self, dashboard_files: list[Path]) -> None:
        """No two dashboards share the same UID."""
        uids = []
        for path in dashboard_files:
            data = load_dashboard(path)
            uids.append((data.get("uid"), path.name))
        uid_values = [u[0] for u in uids]
        duplicates = [u for u in uid_values if uid_values.count(u) > 1]
        assert not duplicates, f"Duplicate UIDs: {set(duplicates)}"

    def test_dashboard_titles_are_unique(self, dashboard_files: list[Path]) -> None:
        """No two dashboards share the same title."""
        titles = []
        for path in dashboard_files:
            data = load_dashboard(path)
            titles.append((data.get("title"), path.name))
        title_values = [t[0] for t in titles]
        duplicates = [t for t in title_values if title_values.count(t) > 1]
        assert not duplicates, f"Duplicate titles: {set(duplicates)}"
