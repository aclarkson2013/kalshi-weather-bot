"""Tests for backend.trading.notifications -- NotificationService web push.

The NotificationService sends web push notifications via VAPID.
It degrades gracefully when pywebpush is not installed or VAPID keys
are not configured.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.trading.notifications import NotificationService


class TestNotificationService:
    """Tests for the NotificationService class."""

    def test_service_creation(self) -> None:
        """NotificationService accepts a subscription dict without error."""
        sub = {
            "endpoint": "https://push.example.com/sub/123",
            "keys": {
                "p256dh": "test-p256dh-key",
                "auth": "test-auth-key",
            },
        }
        svc = NotificationService(subscription=sub)
        assert svc.subscription == sub

    @pytest.mark.asyncio
    async def test_send_without_pywebpush(self) -> None:
        """When pywebpush is not available, send logs a warning and does not crash."""
        sub = {
            "endpoint": "https://push.example.com/sub/123",
            "keys": {"p256dh": "key", "auth": "auth"},
        }
        svc = NotificationService(subscription=sub)

        # Patch _PYWEBPUSH_AVAILABLE to False at the module level
        with patch("backend.trading.notifications._PYWEBPUSH_AVAILABLE", False):
            # Should not raise -- returns early with a warning
            await svc.send(title="Test", body="Body")

    @pytest.mark.asyncio
    async def test_send_without_vapid_keys(self) -> None:
        """When VAPID keys are not configured, send logs a warning and returns."""
        sub = {
            "endpoint": "https://push.example.com/sub/123",
            "keys": {"p256dh": "key", "auth": "auth"},
        }
        svc = NotificationService(subscription=sub)

        # Patch pywebpush as available but settings missing VAPID keys.
        # get_settings is imported locally inside send(), so we patch it
        # at the source module level (backend.common.config.get_settings).
        mock_settings = MagicMock()
        mock_settings.vapid_private_key = ""
        mock_settings.vapid_email = ""

        with (
            patch("backend.trading.notifications._PYWEBPUSH_AVAILABLE", True),
            patch("backend.common.config.get_settings", return_value=mock_settings),
        ):
            # Should not raise -- logs a warning about missing VAPID keys
            await svc.send(title="Test", body="Body")

    @pytest.mark.asyncio
    async def test_send_success_calls_webpush(self) -> None:
        """When pywebpush is available and VAPID configured, webpush is called."""
        sub = {
            "endpoint": "https://push.example.com/sub/123",
            "keys": {"p256dh": "key", "auth": "auth"},
        }
        svc = NotificationService(subscription=sub)

        mock_settings = MagicMock()
        mock_settings.vapid_private_key = "test-private-key"
        mock_settings.vapid_email = "test@example.com"

        mock_webpush_fn = MagicMock()

        with (
            patch("backend.trading.notifications._PYWEBPUSH_AVAILABLE", True),
            patch("backend.common.config.get_settings", return_value=mock_settings),
            patch("backend.trading.notifications.webpush", mock_webpush_fn, create=True),
        ):
            await svc.send(title="Trade Won!", body="+78c", data={"trade_id": "abc"})
            mock_webpush_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_handles_generic_exception(self) -> None:
        """When webpush raises a generic Exception, it is caught and logged."""
        sub = {
            "endpoint": "https://push.example.com/sub/123",
            "keys": {"p256dh": "key", "auth": "auth"},
        }
        svc = NotificationService(subscription=sub)

        mock_settings = MagicMock()
        mock_settings.vapid_private_key = "test-private-key"
        mock_settings.vapid_email = "test@example.com"

        with (
            patch("backend.trading.notifications._PYWEBPUSH_AVAILABLE", True),
            patch("backend.common.config.get_settings", return_value=mock_settings),
            patch(
                "backend.trading.notifications.webpush",
                side_effect=Exception("push failed"),
                create=True,
            ),
        ):
            # Should not raise -- the exception is caught and logged
            await svc.send(title="Test", body="Body")
