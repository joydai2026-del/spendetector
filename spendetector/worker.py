"""The heavy path: one Telegram update -> parse -> Notion -> insight -> reply.

`process_update` is plain Python (no Modal import) so it unit-tests with injected fakes. The
Modal-decorated wrapper lives in app.py and calls this with a real modal.Dict as the seen-set.

Idempotency is two-layer:
  1. an in-memory modal.Dict seen-set on update_id (catches Telegram redelivering the same update);
  2. a durable Notion guard on a sha256 of the image bytes (catches the user RE-SENDING the same
     photo, which Telegram delivers as a brand-new update_id).
The whole heavy path is wrapped so a failure always sends a soft-fail reply, never dead silence.
"""

from __future__ import annotations

import datetime as dt
import hashlib

from . import extract as extract_mod
from . import notion_io, reply, telegram_io
from .config import env_optional
from .insight import compute_insight

_LOW_CONFIDENCE = 0.5


def _photo_file_id(message: dict) -> str | None:
    """Largest photo size, or an image sent as a document/file."""
    photos = message.get("photo")
    if photos:
        return photos[-1]["file_id"]
    doc = message.get("document")
    if doc and str(doc.get("mime_type", "")).startswith("image/"):
        return doc["file_id"]
    return None


def _owner_ok(chat_id) -> bool:
    """Fail closed: only the configured owner is served. Absence of config rejects in prod."""
    allowed = env_optional("TELEGRAM_ALLOWED_CHAT_ID")
    if allowed:
        return str(chat_id) == str(allowed)
    return env_optional("SPENDETECTOR_ALLOW_INSECURE") == "1"


def process_update(update: dict, *, seen=None, deps: dict | None = None) -> dict:
    """Process one update. `deps` injects fakes for extract/notion/telegram in tests."""
    d = deps or {}
    extract = d.get("extract", extract_mod)
    notion = d.get("notion", notion_io)
    telegram = d.get("telegram", telegram_io)

    update_id = update.get("update_id")
    message = update.get("message") or update.get("edited_message") or {}
    chat_id = (message.get("chat") or {}).get("id")

    if not _owner_ok(chat_id):
        return {"status": "rejected", "reason": "unauthorized_chat"}

    # Idempotency layer 1: in-memory seen-set on update_id (same-update redelivery).
    if seen is not None and update_id in seen:
        return {"status": "duplicate"}

    file_id = _photo_file_id(message)
    if not file_id:
        return {"status": "ignored", "reason": "no_photo"}

    try:
        image_bytes = telegram.get_file_bytes(file_id)
        image_hash = hashlib.sha256(image_bytes).hexdigest()

        # Idempotency layer 2: durable guard on the image bytes (same photo re-sent).
        try:
            if notion.find_receipt_by_image_hash(image_hash):
                if seen is not None:
                    seen[update_id] = True
                return {"status": "duplicate"}
        except Exception:
            pass  # best-effort; the seen-set still covers same-update redelivery

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

        result = notion.write_receipt(receipt, update_id, image_hash=image_hash)

        if result.get("failed_items", 0) >= len(receipt.items):
            # Every item failed: do NOT mark seen, so a retry or resend can re-attempt
            # (the dedup guard also ignores failed receipts).
            telegram.send_message(chat_id, reply.failed_reply())
            return {"status": "write_failed", "receipt": result}

        if seen is not None:
            seen[update_id] = True  # mark complete only after a successful or partial write

        low_conf = sum(1 for it in receipt.items if (it.confidence or 1.0) < _LOW_CONFIDENCE)
        telegram.send_message(chat_id, reply.compose_reply(receipt, insight, low_conf=low_conf))
        return {"status": "ok", "insight_kind": insight.kind, "receipt": result}

    except Exception as exc:
        # Never leave the user in silence; this is the demo-day dead-air guard. Log the cause
        # (scrubbed by the io layers) so a failure is diagnosable, not invisible.
        print(f"worker heavy-path error: {type(exc).__name__}: {exc}")
        try:
            telegram.send_message(chat_id, reply.error_reply())
        except Exception as send_exc:
            print(f"soft-fail send also failed: {type(send_exc).__name__}: {send_exc}")
        return {"status": "error", "error": type(exc).__name__}
