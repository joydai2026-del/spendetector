"""Telegram I/O: download a photo's bytes and send a reply.

Telegram embeds the bot token in the request URL, and httpx error messages include that URL. So
every call sanitizes failures into a TelegramError carrying only a status code or error type,
never the URL, so the token can never leak into Modal logs.
"""

from __future__ import annotations

import httpx

from .config import env

_API = "https://api.telegram.org"
_TIMEOUT = 30.0


class TelegramError(RuntimeError):
    """A Telegram call failed; the message is scrubbed of the token-bearing URL."""


def _token() -> str:
    return env("TELEGRAM_BOT_TOKEN")


def _status(exc: httpx.HTTPError) -> str:
    resp = getattr(exc, "response", None)
    return str(resp.status_code) if resp is not None else type(exc).__name__


def get_file_bytes(file_id: str, *, client: httpx.Client | None = None) -> bytes:
    """Resolve a Telegram file_id to its bytes (getFile -> download). Retries once on failure."""
    own = client is None
    c = client or httpx.Client(timeout=_TIMEOUT)
    try:
        token = _token()
        last: httpx.HTTPError | None = None
        for _ in range(2):
            try:
                meta = c.get(f"{_API}/bot{token}/getFile", params={"file_id": file_id})
                meta.raise_for_status()
                file_path = meta.json()["result"]["file_path"]
                blob = c.get(f"{_API}/file/bot{token}/{file_path}")
                blob.raise_for_status()
                return blob.content
            except httpx.HTTPError as exc:
                last = exc
        raise TelegramError(f"getFile failed ({_status(last)})") from None
    finally:
        if own:
            c.close()


def send_message(
    chat_id: int | str,
    text: str,
    *,
    parse_mode: str | None = "HTML",
    client: httpx.Client | None = None,
) -> dict:
    """Send a text reply. HTML parse_mode renders the tap-through link as plain link text."""
    own = client is None
    c = client or httpx.Client(timeout=_TIMEOUT)
    try:
        r = c.post(
            f"{_API}/bot{_token()}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
        )
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as exc:
        raise TelegramError(f"sendMessage failed ({_status(exc)})") from None
    finally:
        if own:
            c.close()
