"""Compose the bot's reply text. One-shot: a confirmation line, one insight, a tap link.

Warm, grandma-simple, no em dashes, no jargon. HTML parse_mode keeps a stray character in an
item name (an &, <, or >) from breaking the message.
"""

from __future__ import annotations

import html

from .config import env_optional
from .extract import Receipt
from .insight import Insight


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def _link(label: str, url: str) -> str:
    if not url:
        return _esc(label)
    return f'<a href="{html.escape(url, quote=True)}">{_esc(label)}</a>'


def compose_reply(
    receipt: Receipt, insight: Insight, *, receipt_url: str | None = None, low_conf: int = 0
) -> str:
    store = receipt.store or "Receipt"
    if receipt.total is not None:
        head = f"{store}, ${receipt.total:.2f}, {len(receipt.items)} items."
    else:
        head = f"{store}, {len(receipt.items)} items."

    lines = [_esc(head), _esc(insight.text)]
    if low_conf:
        noun = "item" if low_conf == 1 else "items"
        lines.append(_esc(f"{low_conf} {noun} were unclear, tap to fix in Notion."))
    # Link to THIS receipt's own report page (items + insights); the report itself links on to
    # the overall dashboard. Fall back to the dashboard if the receipt url is missing.
    url = receipt_url or env_optional("NOTION_DASHBOARD_URL")
    lines.append(_link("See this receipt's report", url))
    return "\n".join(lines)


def greeting_reply() -> str:
    """Sent when the user texts (or taps Start) instead of sending a photo. The bot is a
    one-shot receipt reader, not a chatbot, so any non-photo message gets this gentle nudge
    toward the one thing it does, rather than dead silence (which reads as 'broken')."""
    return (
        "\U0001f50d I'm Spendetector. Snap a photo of any receipt and I'll itemize it for you. "
        "Go ahead, send me one!"
    )


def non_receipt_reply() -> str:
    return (
        "Hmm, I could not read a receipt in that photo. Mind sending it again with the whole "
        "receipt in frame and the text facing up? Good light helps too."
    )


def failed_reply() -> str:
    return "I could not read that one. Try a flatter, brighter photo."


def error_reply() -> str:
    return "Something hiccuped reading that receipt. Mind sending it again?"
