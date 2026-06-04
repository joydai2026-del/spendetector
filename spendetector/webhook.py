"""Webhook authenticity check. Kept tiny and pure so it is unit-testable.

Telegram sends the configured secret in the X-Telegram-Bot-Api-Secret-Token header on every
webhook call. We verify it (constant time) before doing anything. It FAILS CLOSED: if no secret
is configured, the request is rejected unless SPENDETECTOR_ALLOW_INSECURE=1 is set for local dev,
so a misconfigured deploy never serves an open, billable endpoint.
"""

from __future__ import annotations

import hmac

from .config import env_optional


def verify_secret(header_value: str | None) -> bool:
    """True if the request is authentic."""
    expected = env_optional("TELEGRAM_WEBHOOK_SECRET")
    if not expected:
        return env_optional("SPENDETECTOR_ALLOW_INSECURE") == "1"
    return hmac.compare_digest(header_value or "", expected)
