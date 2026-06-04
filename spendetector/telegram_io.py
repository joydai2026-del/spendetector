"""Telegram I/O: download a photo's bytes and send a reply."""

from __future__ import annotations

import httpx

from .config import env

_API = "https://api.telegram.org"
_TIMEOUT = 30.0


def _token() -> str:
    return env("TELEGRAM_BOT_TOKEN")


def get_file_bytes(file_id: str, *, client: httpx.Client | None = None) -> bytes:
    """Resolve a Telegram file_id to its bytes (getFile -> download)."""
    own = client is None
    c = client or httpx.Client(timeout=_TIMEOUT)
    try:
        token = _token()
        meta = c.get(f"{_API}/bot{token}/getFile", params={"file_id": file_id})
        meta.raise_for_status()
        file_path = meta.json()["result"]["file_path"]
        blob = c.get(f"{_API}/file/bot{token}/{file_path}")
        blob.raise_for_status()
        return blob.content
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
    """Send a text reply. Markdown lets the tap-through link render as plain link text."""
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
    finally:
        if own:
            c.close()
