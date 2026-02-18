"""Web push notification service for the trading engine.

Sends real-time push notifications to the user's PWA using VAPID
(Voluntary Application Server Identification) web push protocol.

Notification events:
    - Trade queued (manual mode): "+EV Trade: {city} {bracket}"
    - Trade executed (auto mode): "Trade Placed: {city} {bracket}"
    - Trade settled (win): "Trade Won: {city} +{pnl}c"
    - Trade settled (loss): "Trade Lost: {city} -{pnl}c"
    - Risk limit warning: "Risk Warning"
    - Daily summary: "Daily Summary: {date}"

The push subscription is stored as JSON in the User model's
push_subscription field during PWA onboarding.

Usage:
    from backend.trading.notifications import NotificationService

    svc = NotificationService(subscription=user_push_sub_dict)
    await svc.send(title="Trade Won!", body="NYC +78c", data={"trade_id": "..."})
"""

from __future__ import annotations

import json

from backend.common.logging import get_logger

logger = get_logger("TRADING")

# Attempt to import pywebpush. It may not be installed in all environments
# (e.g., during testing or development without push notification support).
try:
    from pywebpush import WebPushException, webpush

    _PYWEBPUSH_AVAILABLE = True
except ImportError:
    _PYWEBPUSH_AVAILABLE = False
    logger.debug(
        "pywebpush not installed -- push notifications disabled",
        extra={"data": {}},
    )


class NotificationService:
    """Sends web push notifications to a user via VAPID.

    Requires pywebpush to be installed. If not available, send()
    will log a warning and return silently.

    Args:
        subscription: Dict with the user's push subscription info.
            Must contain keys: "endpoint", "keys" (with "p256dh" and "auth").
            This is stored in the user's record during PWA onboarding.
    """

    def __init__(self, subscription: dict) -> None:
        self.subscription = subscription

    async def send(
        self,
        title: str,
        body: str,
        data: dict | None = None,
    ) -> None:
        """Send a web push notification to the user.

        If pywebpush is not installed, logs a warning and returns.
        If VAPID keys are not configured, logs a warning and returns.

        Args:
            title: Notification title (shown in the notification banner).
            body: Notification body text.
            data: Optional JSON-serializable data for the PWA to process on tap.
        """
        if not _PYWEBPUSH_AVAILABLE:
            logger.warning(
                "Push notification skipped: pywebpush not installed",
                extra={"data": {"title": title}},
            )
            return

        from backend.common.config import get_settings

        settings = get_settings()

        if not settings.vapid_private_key or not settings.vapid_email:
            logger.warning(
                "Push notification skipped: VAPID keys not configured",
                extra={"data": {"title": title}},
            )
            return

        payload = json.dumps(
            {
                "title": title,
                "body": body,
                "data": data or {},
            }
        )

        try:
            webpush(
                subscription_info=self.subscription,
                data=payload,
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": f"mailto:{settings.vapid_email}"},
            )
            logger.info(
                "Push notification sent",
                extra={"data": {"title": title}},
            )
        except WebPushException as exc:
            logger.error(
                "Push notification failed",
                extra={"data": {"error": str(exc), "title": title}},
            )
        except Exception as exc:
            logger.error(
                "Unexpected error sending push notification",
                extra={"data": {"error": str(exc), "title": title}},
            )
