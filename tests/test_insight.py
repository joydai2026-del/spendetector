from spendetector.extract import Item
from spendetector.insight import compute_insight


def _item(name, unit_price, total, norm=None, cat="Groceries"):
    return Item(
        name=name, qty=1, unit_price=unit_price, total=total,
        category=cat, confidence=1.0, norm_name=norm or name.lower(),
    )


def test_price_move_fires_with_numbers_and_month():
    items = [_item("Oat Milk", 5.29, 5.29, norm="oat milk")]
    prior = {"oat milk": (4.49, "2026-03-03")}
    ins = compute_insight(items, prior)
    assert ins.kind == "price_move"
    assert "18%" in ins.text          # (5.29-4.49)/4.49 = 0.178
    assert "March" in ins.text
    assert "$4.49" in ins.text and "$5.29" in ins.text


def test_below_threshold_falls_through_to_biggest():
    items = [_item("Oat Milk", 4.59, 4.59, norm="oat milk"), _item("Salmon", 14.99, 14.99, norm="salmon")]
    prior = {"oat milk": (4.49, "2026-03-03")}  # +2.2%, below 10%
    ins = compute_insight(items, prior)
    assert ins.kind == "biggest"
    assert "Salmon" in ins.text


def test_cold_start_never_fabricates_a_delta():
    items = [_item("Oat Milk", 5.29, 5.29, norm="oat milk")]
    ins = compute_insight(items, {})
    assert ins.kind == "cold_start"
    assert "%" not in ins.text


def test_biggest_absolute_mover_wins():
    items = [_item("Oat Milk", 5.29, 5.29, norm="oat milk"), _item("Coffee", 6.00, 6.00, norm="coffee")]
    prior = {"oat milk": (4.49, "2026-03-03"), "coffee": (3.00, "2026-02-01")}  # coffee +100%
    ins = compute_insight(items, prior)
    assert ins.kind == "price_move"
    assert "coffee" in ins.text.lower()


def test_no_em_dashes_in_insight_text():
    ins = compute_insight([_item("Oat Milk", 5.29, 5.29, norm="oat milk")], {})
    assert "—" not in ins.text
