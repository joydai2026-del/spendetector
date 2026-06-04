"""The heavy path: one Telegram update -> parse -> Notion -> insight -> reply.

`process_update` is plain Python (no Modal import) so it unit-tests with injected fakes. The
Modal-decorated wrapper lives in app.py and calls this with a real modal.Dict as the seen-set.

Idempotency is two-layer and ordered so Modal's automatic retries still work:
  1. read the seen-set (fast path) and the Receipts-DB guard (durable) at the top; either hit
     means we already handled this update_id -> stop.
  2. mark the seen-set only AFTER a successful write, so a retry of a pre-write failure re-runs,
     while a redelivery after success is caught by the DB guard.
"""

from __future__ import annotations

import datetime as dt

from . import extract as extract_mod
from . import notion_io, reply, telegram_io
from .config import env_optional
from .insight import compute_insight


def _photo_file_id(message: dict) -> str | None:
    """Largest photo size, or an image sent as a document/file."""
    photos = message.get("photo")
    if photos:
        return photos[-1]["file_id"]
    doc = message.get("document")
    if doc and str(doc.get("mime_type", "")).startswith("image/"):
        return doc["file_id"]
    return None


def process_update(update: dict, *, seen=None, deps: dict | None = None) -> dict:
    """Process one update. `deps` injects fakes for extract/notion/telegram in tests."""
    d = deps or {}
    extract = d.get("extract", extract_mod)
    notion = d.get("notion", notion_io)
    telegram = d.get("telegram", telegram_io)

    update_id = update.get("update_id")
    message = update.get("message") or update.get("edited_message") or {}
    chat_id = (message.get("chat") or {}).get("id")

    # Owner gate: this is a personal app; ignore anyone else who finds the bot.
    allowed = env_optional("TELEGRAM_ALLOWED_CHAT_ID")
    if allowed and str(chat_id) != str(allowed):
        return {"status": "rejected", "reason": "unauthorized_chat"}

    # Idempotency layer 1a: seen-set fast path.
    if seen is not None and update_id in seen:
        return {"status": "duplicate"}

    file_id = _photo_file_id(message)
    if not file_id:
        return {"status": "ignored", "reason": "no_photo"}

    # Idempotency layer 1b: durable DB guard (catches redelivery after a prior success).
    try:
        if notion.find_receipt_by_update_id(update_id):
            return {"status": "duplicate"}
    except Exception:
        pass  # best-effort; the seen-set still covers the common case

    image_bytes = telegram.get_file_bytes(file_id)
    receipt = extract.parse_receipt(image_bytes)

    if not receipt.is_receipt:
        telegram.send_message(chat_id, reply.non_receipt_reply())
        return {"status": "not_receipt"}
    if not receipt.items:
        telegram.send_message(chat_id, reply.failed_reply())
        return {"status": "empty"}

    # Prior prices BEFORE writing, so this receipt's own rows never become their own "prior".
    eff_date = receipt.date or dt.date.today().isoformat()
    prior = notion.fetch_prior_prices(receipt.items, eff_date)
    insight = compute_insight(receipt.items, prior)

    result = notion.write_receipt(receipt, update_id)

    if seen is not None:
        seen[update_id] = True  # mark complete only after the write succeeded

    telegram.send_message(chat_id, reply.compose_reply(receipt, insight))
    return {"status": "ok", "insight_kind": insight.kind, "receipt": result}
