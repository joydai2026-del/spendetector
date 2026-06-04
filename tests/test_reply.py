from spendetector import reply
from spendetector.extract import Item, Receipt
from spendetector.insight import Insight


def _receipt(total=42.10, n=3, store="Whole Foods"):
    items = [Item(f"Item {i}", 1, 1.0, 1.0, "Groceries", 1.0, f"item {i}") for i in range(n)]
    return Receipt(is_receipt=True, store=store, date="2026-06-04", items=items,
                   subtotal=total, tax=0.0, total=total)


def test_price_move_reply_has_confirmation_insight_and_link():
    r = _receipt()
    ins = Insight("Heads up: your oat milk crept up 18% since March, from $4.49 to $5.29.", "price_move")
    text = reply.compose_reply(r, ins)
    assert "Whole Foods, $42.10, 3 items." in text
    assert "See the price trend" in text
    assert '<a href="https://www.notion.so/spendetector">' in text


def test_cold_start_link_label():
    ins = Insight("Saved. This is your first scan, so I am learning your prices now.", "cold_start")
    text = reply.compose_reply(_receipt(), ins)
    assert "See your spending so far" in text


def test_html_escapes_special_chars_in_store():
    r = _receipt(store="Ben & Jerry's")
    ins = Insight("Biggest item: Ben & Jerry's at $5.00.", "biggest")
    text = reply.compose_reply(r, ins)
    assert "&amp;" in text  # the ampersand is escaped, so it cannot break HTML parse_mode


def test_no_em_dashes_in_static_replies():
    assert "—" not in reply.non_receipt_reply()
    assert "—" not in reply.failed_reply()
