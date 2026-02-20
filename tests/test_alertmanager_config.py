"""Validation tests for Alertmanager configuration.

Ensures the alertmanager.yml file is well-formed and has the expected
routing, receiver, and inhibit_rules structure.  Static YAML validation
only — never hits a live Alertmanager instance.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

# ─── Constants ───

ALERTMANAGER_CONFIG = (
    Path(__file__).resolve().parent.parent / "monitoring" / "alertmanager" / "alertmanager.yml"
)


# ─── Fixtures ───


@pytest.fixture
def config() -> dict:
    """Load and parse the alertmanager.yml file."""
    text = ALERTMANAGER_CONFIG.read_text(encoding="utf-8")
    return yaml.safe_load(text)


# ─── Tests ───


class TestAlertmanagerFileExists:
    """Verify the config file is present and valid YAML."""

    def test_config_file_exists(self) -> None:
        """alertmanager.yml exists in the expected location."""
        assert ALERTMANAGER_CONFIG.is_file(), f"Missing config: {ALERTMANAGER_CONFIG}"

    def test_valid_yaml(self) -> None:
        """alertmanager.yml is valid YAML."""
        text = ALERTMANAGER_CONFIG.read_text(encoding="utf-8")
        try:
            yaml.safe_load(text)
        except yaml.YAMLError as exc:
            pytest.fail(f"Invalid YAML: {exc}")


class TestRouteConfig:
    """Validate the routing configuration."""

    def test_has_route_section(self, config: dict) -> None:
        """Config has a top-level 'route' section."""
        assert "route" in config, "Missing 'route' section"

    def test_route_has_receiver(self, config: dict) -> None:
        """Default route specifies a receiver."""
        route = config.get("route", {})
        assert "receiver" in route, "Default route missing 'receiver'"

    def test_route_groups_by_alertname(self, config: dict) -> None:
        """Default route groups by alertname."""
        route = config.get("route", {})
        group_by = route.get("group_by", [])
        assert "alertname" in group_by, f"group_by missing 'alertname': {group_by}"

    def test_route_groups_by_severity(self, config: dict) -> None:
        """Default route groups by severity."""
        route = config.get("route", {})
        group_by = route.get("group_by", [])
        assert "severity" in group_by, f"group_by missing 'severity': {group_by}"


class TestReceivers:
    """Validate the receivers configuration."""

    def test_has_receivers_section(self, config: dict) -> None:
        """Config has a 'receivers' section."""
        assert "receivers" in config, "Missing 'receivers' section"

    def test_at_least_one_receiver(self, config: dict) -> None:
        """At least one receiver is defined."""
        receivers = config.get("receivers", [])
        assert len(receivers) >= 1, "No receivers defined"

    def test_receiver_has_webhook_config(self, config: dict) -> None:
        """At least one receiver has webhook_configs."""
        receivers = config.get("receivers", [])
        has_webhook = any("webhook_configs" in r for r in receivers)
        assert has_webhook, "No receiver has webhook_configs"

    def test_webhook_has_url(self, config: dict) -> None:
        """Every webhook_configs entry has a url."""
        for receiver in config.get("receivers", []):
            for wh in receiver.get("webhook_configs", []):
                assert "url" in wh, f"Webhook in '{receiver.get('name', '?')}' missing 'url'"


class TestInhibitRules:
    """Validate the inhibit_rules configuration."""

    def test_has_inhibit_rules(self, config: dict) -> None:
        """Config has an 'inhibit_rules' section."""
        assert "inhibit_rules" in config, "Missing 'inhibit_rules' section"

    def test_at_least_one_inhibit_rule(self, config: dict) -> None:
        """At least one inhibit rule is defined."""
        rules = config.get("inhibit_rules", [])
        assert len(rules) >= 1, "No inhibit rules defined"

    def test_inhibit_rules_have_source_and_target(self, config: dict) -> None:
        """Each inhibit rule has source_match and target_match."""
        for i, rule in enumerate(config.get("inhibit_rules", [])):
            assert "source_match" in rule, f"Inhibit rule {i} missing 'source_match'"
            assert "target_match" in rule, f"Inhibit rule {i} missing 'target_match'"

    def test_inhibit_rules_have_equal_field(self, config: dict) -> None:
        """Each inhibit rule has an 'equal' field for matching."""
        for i, rule in enumerate(config.get("inhibit_rules", [])):
            assert "equal" in rule, f"Inhibit rule {i} missing 'equal' field"
