"""Compose the bot's reply text. One-shot: a confirmation line, one insight, a tap link.

Warm, grandma-simple, no em dashes, no jargon. HTML parse_mode keeps a stray character in an
item name (an &, <, or >) from breaking the message.
"""

from __future__ import annotations

import html

from .config import env_optional
from .extract import Receipt
from .insight import Insight

_LINK_LABELS = {
    "price_move": "See the price trend",
    "cold_start": "See your spending so far",
}
_DEFAULT_LABEL = "See your spending"


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def _url_for(kind: str) -> str:
    # The price-creep reply deep-links to the per-item price view if one is configured, so the
    # tap pays off the sentence; otherwise it falls back to the dashboard top (hero callout).
    if kind == "price_move":
        return env_optional("NOTION_PRICE_VIEW_URL") or env_optional("NOTION_DASHBOARD_URL")
    return env_optional("NOTION_DASHBOARD_URL")


def _link(label: str, url: str) -> str:
    if not url:
        return _esc(label)
    return f'<a href="{html.escape(url, quote=True)}">{_esc(label)}</a>'


def compose_reply(receipt: Receipt, insight: Insight, *, low_conf: int = 0) -> str:
    store = receipt.store or "Receipt"
    if receipt.total is not None:
        head = f"{store}, ${receipt.total:.2f}, {len(receipt.items)} items."
    else:
        head = f"{store}, {len(receipt.items)} items."

    lines = [_esc(head), _esc(insight.text)]
    if low_conf:
        noun = "item" if low_conf == 1 else "items"
        lines.append(_esc(f"{low_conf} {noun} were unclear, tap to fix in Notion."))
    lines.append(_link(_LINK_LABELS.get(insight.kind, _DEFAULT_LABEL), _url_for(insight.kind)))
    return "\n".join(lines)


def non_receipt_reply() -> str:
    return (
        "Hmm, I could not read a receipt in that photo. Mind sending it again with the whole "
        "receipt in frame and the text facing up? Good light helps too."
    )


def failed_reply() -> str:
    return "I could not read that one. Try a flatter, brighter photo."


def error_reply() -> str:
    return "Something hiccuped reading that receipt. Mind sending it again?"
