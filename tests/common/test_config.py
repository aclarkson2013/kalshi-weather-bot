"""Tests for application configuration."""

from __future__ import annotations

import os

import pytest

from backend.common.config import Settings, get_settings


class TestSettings:
    """Test Settings loading from environment variables."""

    def test_settings_loads(self):
        """Settings can be instantiated from environment."""
        settings = get_settings()
        assert settings is not None

    def test_encryption_key_from_env(self):
        """Encryption key is loaded from ENCRYPTION_KEY env var."""
        settings = get_settings()
        assert settings.encryption_key is not None
        assert len(settings.encryption_key) > 0

    def test_database_url_from_env(self):
        """Database URL is loaded from DATABASE_URL env var."""
        settings = get_settings()
        assert settings.database_url is not None

    def test_environment_defaults_to_testing(self):
        """In tests, environment is set to 'testing' by conftest."""
        settings = get_settings()
        # conftest.py sets ENVIRONMENT=testing
        assert settings.environment == "testing"

    def test_trading_defaults(self):
        """Default trading values are safe small amounts."""
        settings = get_settings()
        assert settings.default_max_trade_size == 1.00
        assert settings.default_daily_loss_limit == 10.00
        assert settings.default_max_daily_exposure == 25.00
        assert settings.default_min_ev_threshold == 0.05
        assert settings.default_cooldown_minutes == 60
        assert settings.default_consecutive_loss_limit == 3

    def test_nws_defaults(self):
        """NWS API defaults are set."""
        settings = get_settings()
        assert "BozWeatherTrader" in settings.nws_user_agent
        assert settings.nws_rate_limit_per_second == 1.0

    def test_settings_singleton(self):
        """get_settings returns the same cached instance."""
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_db_pool_defaults(self):
        """Database pool settings have sensible defaults."""
        settings = get_settings()
        assert settings.db_pool_size == 10
        assert settings.db_max_overflow == 20

    def test_missing_encryption_key_raises(self):
        """Settings fails if ENCRYPTION_KEY is not set."""
        # Clear the cache
        get_settings.cache_clear()

        # Temporarily remove the env var
        original = os.environ.pop("ENCRYPTION_KEY", None)
        try:
            with pytest.raises(Exception):
                Settings()
        finally:
            # Restore for other tests
            if original is not None:
                os.environ["ENCRYPTION_KEY"] = original
            get_settings.cache_clear()  # Re-cache with correct settings
