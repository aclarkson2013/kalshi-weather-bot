"""Tests for structured logging setup."""

from __future__ import annotations

from backend.common.logging import _redact_secrets, get_logger


class TestGetLogger:
    """Test logger creation and configuration."""

    def test_returns_logger_adapter(self):
        """get_logger returns a ModuleTagLogger adapter."""
        logger = get_logger("TEST")
        assert logger is not None

    def test_same_tag_returns_same_logger(self):
        """Calling get_logger twice with same tag returns the same instance."""
        logger1 = get_logger("WEATHER")
        logger2 = get_logger("WEATHER")
        assert logger1 is logger2

    def test_different_tags_return_different_loggers(self):
        """Different tags produce different logger instances."""
        logger1 = get_logger("WEATHER")
        logger2 = get_logger("TRADING")
        assert logger1 is not logger2

    def test_log_output_contains_module_tag(self, capfd):
        """Log output includes the module tag."""
        logger = get_logger("ORDER")
        logger.info("Test message")
        captured = capfd.readouterr()
        assert "ORDER" in captured.out

    def test_log_output_contains_message(self, capfd):
        """Log output includes the message text."""
        logger = get_logger("SYSTEM")
        logger.info("System started")
        captured = capfd.readouterr()
        assert "System started" in captured.out

    def test_log_output_contains_level(self, capfd):
        """Log output includes the log level."""
        logger = get_logger("RISK")
        logger.warning("Risk limit approaching")
        captured = capfd.readouterr()
        assert "WARNING" in captured.out

    def test_structured_data_in_output(self, capfd):
        """Structured data dict appears in log output."""
        logger = get_logger("MARKET")
        logger.info("Market price", extra={"data": {"city": "NYC", "price": 22}})
        captured = capfd.readouterr()
        assert "NYC" in captured.out
        assert "22" in captured.out


class TestSecretRedaction:
    """Test that secrets are redacted from log output."""

    def test_redact_api_key(self):
        """Values for keys containing 'key' are redacted."""
        text = '{"api_key": "super-secret-123"}'
        redacted = _redact_secrets(text)
        assert "super-secret-123" not in redacted
        assert "[REDACTED]" in redacted

    def test_redact_private_key(self):
        """Values for keys containing 'private' are redacted."""
        text = '{"private_key": "-----BEGIN RSA PRIVATE KEY-----"}'
        redacted = _redact_secrets(text)
        assert "BEGIN RSA" not in redacted
        assert "[REDACTED]" in redacted

    def test_redact_password(self):
        """Values for keys containing 'password' are redacted."""
        text = '{"password": "hunter2"}'
        redacted = _redact_secrets(text)
        assert "hunter2" not in redacted

    def test_redact_token(self):
        """Values for keys containing 'token' are redacted."""
        text = '{"auth_token": "eyJhbGciOiJIUzI1NiJ9"}'
        redacted = _redact_secrets(text)
        assert "eyJhbG" not in redacted

    def test_non_secret_fields_preserved(self):
        """Non-secret fields are not redacted."""
        text = '{"city": "NYC", "temperature": "56"}'
        redacted = _redact_secrets(text)
        assert "NYC" in redacted
        assert "56" in redacted

    def test_secret_redaction_in_log_output(self, capfd):
        """Secrets in structured data are redacted in actual log output."""
        logger = get_logger("AUTH")
        logger.info(
            "Auth attempt",
            extra={"data": {"api_key": "real-secret-key-value", "city": "NYC"}},
        )
        captured = capfd.readouterr()
        assert "real-secret-key-value" not in captured.out
        assert "NYC" in captured.out
