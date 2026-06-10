from spendetector import reply
from spendetector.extract import Item, Receipt
from spendetector.insight import Insight


def _receipt(total=42.10, n=3, store="Whole Foods"):
    items = [Item(f"Item {i}", 1, 1.0, 1.0, "Groceries", 1.0, f"item {i}") for i in range(n)]
    return Receipt(is_receipt=True, store=store, date="2026-06-04", items=items,
                   subtotal=total, tax=0.0, total=total)


def test_reply_links_to_this_receipts_report():
    r = _receipt()
    ins = Insight("Heads up: your oat milk crept up 18% since March, from $4.49 to $5.29.", "price_move")
    text = reply.compose_reply(r, ins, receipt_url="https://www.notion.so/receipt-abc")
    assert "Whole Foods, $42.10, 3 items." in text
    assert "See this receipt's report" in text
    assert '<a href="https://www.notion.so/receipt-abc">' in text  # the receipt's own page


def test_reply_falls_back_to_dashboard_when_no_receipt_url():
    ins = Insight("Saved.", "cold_start")
    text = reply.compose_reply(_receipt(), ins)  # no receipt_url
    assert '<a href="https://www.notion.so/spendetector">' in text  # conftest dashboard url


def test_html_escapes_special_chars_in_store():
    r = _receipt(store="Ben & Jerry's")
    ins = Insight("Biggest item: Ben & Jerry's at $5.00.", "biggest")
    text = reply.compose_reply(r, ins)
    assert "&amp;" in text  # the ampersand is escaped, so it cannot break HTML parse_mode


def test_no_em_dashes_in_static_replies():
    em_dash = "\u2014"
    assert em_dash not in reply.non_receipt_reply()
    assert em_dash not in reply.failed_reply()
    assert em_dash not in reply.greeting_reply()
    assert em_dash not in reply.error_reply()


def test_greeting_reply_nudges_toward_a_receipt():
    text = reply.greeting_reply()
    assert "receipt" in text.lower()
    assert "Spendetector" in text
