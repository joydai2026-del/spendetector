"""Webhook authenticity check. Kept tiny and pure so it is unit-testable.

Telegram sends the configured secret in the X-Telegram-Bot-Api-Secret-Token header on every
webhook call. We verify it before doing anything. The Modal endpoint (app.py) calls this, then
spawns the worker and ACKs fast.
"""

from __future__ import annotations

from .config import env_optional


def verify_secret(header_value: str | None) -> bool:
    """True if the request is authentic. If no secret is configured (local dev), allow."""
    expected = env_optional("TELEGRAM_WEBHOOK_SECRET")
    if not expected:
        return True
    return header_value == expected
