"""Validation tests for Prometheus alerting rule YAML files.

Ensures all alert rules are well-formed, reference real Prometheus metrics,
and follow the project's alerting conventions.  Same static-validation
pattern as test_grafana_dashboards.py — loads files from disk, validates
structure, never hits Prometheus.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

# ─── Constants ───

RULES_DIR = Path(__file__).resolve().parent.parent / "monitoring" / "prometheus" / "rules"

# Metric names defined in backend/common/metrics.py.
# PromQL expressions must reference at least one of these.
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
    "ws_connections_active",
    "ws_messages_sent_total",
    "ws_events_received_total",
    "kalshi_ws_connected",
    "kalshi_ws_messages_total",
    "kalshi_ws_reconnects_total",
    "kalshi_ws_cache_hits_total",
    "weather_fetches_total",
}

# Prometheus built-in metric used in target-health rules.
BUILTIN_METRICS = {"up"}

ALL_KNOWN_METRICS = KNOWN_METRICS | BUILTIN_METRICS

# Prometheus histogram suffixes auto-generated for histogram metrics.
HISTOGRAM_SUFFIXES = {"_bucket", "_count", "_sum"}

VALID_SEVERITIES = {"critical", "warning", "info"}

# Prometheus duration regex: e.g. 1m, 5m, 30m, 1h, 2h, 1d
PROMETHEUS_DURATION_RE = re.compile(r"^\d+[smhdwy]$")

EXPECTED_RULE_COUNT = 17


# ─── Helpers ───


def collect_rule_files() -> list[Path]:
    """Return all .yml files in the rules directory."""
    return sorted(RULES_DIR.glob("*.yml"))


def load_rule_file(path: Path) -> dict:
    """Load and parse a rule YAML file."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def collect_all_rules() -> list[tuple[str, dict]]:
    """Return all (filename, rule) tuples across all rule files."""
    rules: list[tuple[str, dict]] = []
    for path in collect_rule_files():
        data = load_rule_file(path)
        for group in data.get("groups", []):
            for rule in group.get("rules", []):
                rules.append((path.name, rule))
    return rules


def metric_name_in_expr(metric: str, expr: str) -> bool:
    """Check if a metric name (with optional suffixes) appears in a PromQL expression."""
    if metric in expr:
        return True
    return any(f"{metric}{suffix}" in expr for suffix in HISTOGRAM_SUFFIXES)


# ─── Fixtures ───


@pytest.fixture
def rule_files() -> list[Path]:
    """Return all rule YAML file paths."""
    return collect_rule_files()


@pytest.fixture(params=collect_rule_files(), ids=lambda p: p.stem)
def rule_path(request: pytest.FixtureRequest) -> Path:
    """Parametrize tests over each rule file."""
    return request.param


@pytest.fixture
def rule_data(rule_path: Path) -> dict:
    """Load a single rule file as a dict."""
    return load_rule_file(rule_path)


@pytest.fixture
def all_rules() -> list[tuple[str, dict]]:
    """Return all (filename, rule) tuples."""
    return collect_all_rules()


# ─── Tests: Directory & File Discovery ───


class TestRuleDiscovery:
    """Verify rule files exist and are discoverable."""

    def test_rules_directory_exists(self) -> None:
        """The monitoring/prometheus/rules/ directory exists."""
        assert RULES_DIR.is_dir(), f"Missing rules dir: {RULES_DIR}"

    def test_at_least_five_rule_files_exist(self, rule_files: list[Path]) -> None:
        """At least 5 rule YAML files are present (http, celery, trading, weather, targets)."""
        assert len(rule_files) >= 6, f"Expected >= 6 rule files, found {len(rule_files)}"

    def test_expected_rule_files_present(self, rule_files: list[Path]) -> None:
        """All expected rule files are present."""
        names = {p.stem for p in rule_files}
        expected = {"http", "celery", "trading", "weather", "targets", "kalshi_ws"}
        missing = expected - names
        assert not missing, f"Missing rule files: {missing}"


# ─── Tests: YAML Structure ───


class TestRuleFileStructure:
    """Validate YAML structure of each rule file."""

    def test_valid_yaml(self, rule_path: Path) -> None:
        """Rule file is valid YAML."""
        text = rule_path.read_text(encoding="utf-8")
        try:
            yaml.safe_load(text)
        except yaml.YAMLError as exc:
            pytest.fail(f"{rule_path.name}: Invalid YAML — {exc}")

    def test_has_groups_key(self, rule_data: dict) -> None:
        """Rule file has a top-level 'groups' key."""
        assert "groups" in rule_data, "Missing top-level 'groups' key"

    def test_groups_is_non_empty_list(self, rule_data: dict) -> None:
        """The 'groups' key contains a non-empty list."""
        groups = rule_data.get("groups", [])
        assert isinstance(groups, list) and len(groups) > 0, "groups must be a non-empty list"

    def test_each_group_has_name_and_rules(self, rule_data: dict) -> None:
        """Each group has 'name' and 'rules' keys."""
        for group in rule_data.get("groups", []):
            assert "name" in group, "Group missing 'name'"
            assert "rules" in group, f"Group '{group.get('name', '?')}' missing 'rules'"

    def test_each_group_has_at_least_one_rule(self, rule_data: dict) -> None:
        """Each group has at least one rule."""
        for group in rule_data.get("groups", []):
            rules = group.get("rules", [])
            assert len(rules) > 0, f"Group '{group.get('name', '?')}' has no rules"


# ─── Tests: Individual Rule Validation ───


class TestRuleFields:
    """Validate required fields on every alert rule."""

    def test_every_rule_has_alert_name(self, all_rules: list[tuple[str, dict]]) -> None:
        """Every rule has an 'alert' field with a non-empty string."""
        for filename, rule in all_rules:
            alert = rule.get("alert")
            assert isinstance(alert, str) and len(alert) > 0, (
                f"{filename}: rule missing 'alert' name"
            )

    def test_every_rule_has_expr(self, all_rules: list[tuple[str, dict]]) -> None:
        """Every rule has an 'expr' field with a non-empty string."""
        for filename, rule in all_rules:
            expr = rule.get("expr")
            assert isinstance(expr, str) and len(expr.strip()) > 0, (
                f"{filename}/{rule.get('alert', '?')}: missing 'expr'"
            )

    def test_every_rule_has_for_duration(self, all_rules: list[tuple[str, dict]]) -> None:
        """Every rule has a 'for' field with a valid Prometheus duration."""
        for filename, rule in all_rules:
            for_val = rule.get("for")
            assert isinstance(for_val, str), (
                f"{filename}/{rule.get('alert', '?')}: missing 'for' duration"
            )
            assert PROMETHEUS_DURATION_RE.match(for_val), (
                f"{filename}/{rule.get('alert', '?')}: invalid duration '{for_val}'"
            )

    def test_every_rule_has_severity_label(self, all_rules: list[tuple[str, dict]]) -> None:
        """Every rule has labels.severity."""
        for filename, rule in all_rules:
            severity = rule.get("labels", {}).get("severity")
            assert severity is not None, (
                f"{filename}/{rule.get('alert', '?')}: missing labels.severity"
            )

    def test_severity_is_valid(self, all_rules: list[tuple[str, dict]]) -> None:
        """Every rule's severity is one of critical, warning, info."""
        for filename, rule in all_rules:
            severity = rule.get("labels", {}).get("severity", "")
            assert severity in VALID_SEVERITIES, (
                f"{filename}/{rule.get('alert', '?')}: invalid severity '{severity}'"
            )

    def test_every_rule_has_summary_annotation(self, all_rules: list[tuple[str, dict]]) -> None:
        """Every rule has annotations.summary."""
        for filename, rule in all_rules:
            summary = rule.get("annotations", {}).get("summary")
            assert isinstance(summary, str) and len(summary) > 0, (
                f"{filename}/{rule.get('alert', '?')}: missing annotations.summary"
            )

    def test_every_rule_has_description_annotation(self, all_rules: list[tuple[str, dict]]) -> None:
        """Every rule has annotations.description."""
        for filename, rule in all_rules:
            desc = rule.get("annotations", {}).get("description")
            assert isinstance(desc, str) and len(desc.strip()) > 0, (
                f"{filename}/{rule.get('alert', '?')}: missing annotations.description"
            )


# ─── Tests: PromQL References Known Metrics ───


class TestPromQLReferencesMetrics:
    """Verify PromQL expressions reference real metrics from metrics.py."""

    def test_every_expr_references_known_metric(self, all_rules: list[tuple[str, dict]]) -> None:
        """Each PromQL expression references at least one known metric name."""
        for filename, rule in all_rules:
            expr = rule.get("expr", "")
            found = any(metric_name_in_expr(m, expr) for m in ALL_KNOWN_METRICS)
            assert found, (
                f"{filename}/{rule.get('alert', '?')}: expr references no known metric: {expr}"
            )


# ─── Tests: Cross-File Validation ───


class TestCrossFileValidation:
    """Cross-file checks — uniqueness, counts."""

    def test_no_duplicate_alert_names(self, all_rules: list[tuple[str, dict]]) -> None:
        """Alert names are unique across all rule files."""
        names = [rule.get("alert") for _, rule in all_rules]
        duplicates = [n for n in names if names.count(n) > 1]
        assert not duplicates, f"Duplicate alert names: {set(duplicates)}"

    def test_total_rule_count(self, all_rules: list[tuple[str, dict]]) -> None:
        """Total number of rules matches expected count."""
        assert len(all_rules) == EXPECTED_RULE_COUNT, (
            f"Expected {EXPECTED_RULE_COUNT} rules, found {len(all_rules)}"
        )

    def test_group_names_are_unique(self, rule_files: list[Path]) -> None:
        """Group names are unique across all rule files."""
        group_names: list[str] = []
        for path in rule_files:
            data = load_rule_file(path)
            for group in data.get("groups", []):
                group_names.append(group.get("name", ""))
        duplicates = [n for n in group_names if group_names.count(n) > 1]
        assert not duplicates, f"Duplicate group names: {set(duplicates)}"


# ─── Tests: Severity Distribution ───


class TestSeverityDistribution:
    """Verify the alert set has a reasonable severity mix."""

    def test_has_critical_alerts(self, all_rules: list[tuple[str, dict]]) -> None:
        """At least one critical severity alert exists."""
        critical = [r for _, r in all_rules if r.get("labels", {}).get("severity") == "critical"]
        assert len(critical) >= 1, "No critical alerts found"

    def test_has_warning_alerts(self, all_rules: list[tuple[str, dict]]) -> None:
        """At least one warning severity alert exists."""
        warnings = [r for _, r in all_rules if r.get("labels", {}).get("severity") == "warning"]
        assert len(warnings) >= 1, "No warning alerts found"

    def test_has_info_alerts(self, all_rules: list[tuple[str, dict]]) -> None:
        """At least one info severity alert exists."""
        infos = [r for _, r in all_rules if r.get("labels", {}).get("severity") == "info"]
        assert len(infos) >= 1, "No info alerts found"
