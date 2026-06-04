"""Generate 10 realistic grocery receipt images (with real rendered text) for testing.

Rendered, not AI-image-generated, so the text/numbers are crisp and we have ground truth to
verify the extraction. Profile: lots of dairy, nuts, chicken/steak, veggies, fruit. A few
staples drift up in price across the 10 weeks so the demo's price-creep insight fires, and a
masked card line is included to test that card digits are never stored.

    python scripts/make_test_receipts.py
Outputs testdata/receipts/receipt_01.png ... receipt_10.png + manifest.json (ground truth).
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import random

from PIL import Image, ImageDraw, ImageFont

OUT = pathlib.Path(__file__).resolve().parent.parent / "testdata" / "receipts"
WEEKS = 10
FIRST_FRIDAY = dt.date(2026, 3, 27)  # 10 weekly receipts: 2026-03-27 .. 2026-05-29
STORES = ["WHOLE FOODS MARKET", "TRADER JOE'S", "SPROUTS FARMERS MARKET", "SAFEWAY", "COSTCO WHOLESALE"]

# Staples on (almost) every receipt. Linear drift from week 0 to week 9 = the price-creep story.
STAPLES = [
    # name, category, price_week0, price_week9, by_weight
    ("Oat Milk 64oz", "dairy", 4.49, 5.29, False),
    ("Eggs Large Dozen", "dairy", 3.99, 5.49, False),
    ("Chicken Breast", "protein", 5.99, 6.99, True),
    ("Greek Yogurt 32oz", "dairy", 5.49, 5.99, False),
    ("Bananas", "fruit", 0.59, 0.69, True),
]

# Rotating extras (stable prices). name, category, price, by_weight
EXTRAS = [
    ("Whole Milk Gallon", "dairy", 3.79, False), ("Cheddar Cheese", "dairy", 5.99, False),
    ("Unsalted Butter", "dairy", 4.99, False), ("Cream Cheese", "dairy", 2.99, False),
    ("Raw Almonds 16oz", "nuts", 7.99, False), ("Cashews 16oz", "nuts", 8.49, False),
    ("Peanut Butter", "nuts", 4.29, False), ("Walnuts 12oz", "nuts", 7.49, False),
    ("Ribeye Steak", "protein", 14.99, True), ("Ground Beef", "protein", 6.49, True),
    ("Salmon Fillet", "protein", 11.99, True), ("Baby Spinach", "veggie", 3.99, False),
    ("Broccoli Crown", "veggie", 2.49, True), ("Bell Peppers", "veggie", 3.49, False),
    ("Avocado", "veggie", 1.99, False), ("Sweet Potato", "veggie", 1.29, True),
    ("Carrots 2lb", "veggie", 1.79, False), ("Roma Tomatoes", "veggie", 3.29, True),
    ("Strawberries 1lb", "fruit", 4.49, False), ("Blueberries Pint", "fruit", 4.99, False),
    ("Honeycrisp Apples", "fruit", 3.49, True), ("Navel Oranges", "fruit", 3.99, True),
    ("Red Grapes", "fruit", 4.49, True), ("Coffee Beans 12oz", "other", 12.99, False),
    ("Olive Oil 500ml", "other", 9.99, False), ("Paper Towels 6pk", "household", 7.99, False),
    ("Dish Soap", "household", 3.99, False),
]


def load_font(size: int):
    for c in ("/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/Monaco.ttf",
              "/System/Library/Fonts/Supplemental/Courier New.ttf", "/Library/Fonts/Courier New.ttf"):
        try:
            return ImageFont.truetype(c, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _price(base0: float, base9: float, week: int) -> float:
    return round(base0 + (base9 - base0) * week / (WEEKS - 1), 2)


def build_basket(week: int) -> list[dict]:
    rng = random.Random(week * 7 + 3)
    items: list[dict] = []
    for name, cat, p0, p9, by_w in STAPLES:
        if name == "Greek Yogurt 32oz" and rng.random() < 0.25:
            continue  # the occasional skipped staple keeps it realistic
        items.append(_line(name, cat, _price(p0, p9, week), by_w, rng))
    for name, cat, price, by_w in rng.sample(EXTRAS, k=rng.randint(5, 8)):
        jitter = round(price * rng.uniform(-0.04, 0.04), 2)
        items.append(_line(name, cat, round(price + jitter, 2), by_w, rng))
    return items


def _line(name: str, cat: str, unit_price: float, by_weight: bool, rng: random.Random) -> dict:
    if by_weight:
        qty = round(rng.uniform(0.8, 2.4), 2)
    else:
        qty = rng.choice([1, 1, 1, 1, 2])
    total = round(unit_price * qty, 2)
    return {"name": name, "category": cat, "qty": qty, "unit_price": unit_price,
            "total": total, "by_weight": by_weight}


def render(store: str, date: dt.date, items: list[dict], subtotal: float, tax: float,
           total: float, card: str | None, path: pathlib.Path) -> None:
    W, pad, lh = 460, 24, 24
    f = load_font(17)
    fb = load_font(20)
    rows = 8 + sum(2 if it["by_weight"] else 1 for it in items) + (1 if card else 0)
    H = pad * 2 + rows * lh + 40
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    y = pad

    def center(text, font=f, dy=lh):
        nonlocal y
        w = d.textlength(text, font=font)
        d.text(((W - w) / 2, y), text, fill="black", font=font)
        y += dy

    def sep():
        nonlocal y
        d.text((pad, y), "-" * 34, fill="black", font=f)
        y += lh

    def kv(left, right, font=f):
        nonlocal y
        d.text((pad, y), left, fill="black", font=font)
        rw = d.textlength(right, font=font)
        d.text((W - pad - rw, y), right, fill="black", font=font)
        y += lh

    center(store, fb)
    center(f"{1 + (hash(store) % 980)} Market Street")
    center("Tel (555) 012-3456")
    sep()
    kv(date.isoformat(), f"{9 + (date.day % 9)}:{10 + (date.day % 49):02d}")
    sep()
    for it in items:
        if it["by_weight"]:
            d.text((pad, y), it["name"], fill="black", font=f)
            y += lh
            kv(f"  {it['qty']} lb @ {it['unit_price']:.2f}/lb", f"{it['total']:.2f}")
        else:
            label = it["name"] if it["qty"] == 1 else f"{it['name']} x{it['qty']}"
            kv(label, f"{it['total']:.2f}")
    sep()
    kv("SUBTOTAL", f"{subtotal:.2f}")
    kv("TAX", f"{tax:.2f}")
    kv("TOTAL", f"{total:.2f}", fb)
    if card:
        kv(card, f"{total:.2f}")
    center("THANK YOU FOR SHOPPING!")
    img.save(path)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for i in range(WEEKS):
        date = FIRST_FRIDAY + dt.timedelta(weeks=i)
        store = STORES[i % len(STORES)]
        items = build_basket(i)
        subtotal = round(sum(it["total"] for it in items), 2)
        tax = round(sum(it["total"] for it in items if it["category"] == "household") * 0.0875, 2)
        total = round(subtotal + tax, 2)
        card = ["VISA ****4821", "DEBIT ****7193", None, "VISA ****4821", None][i % 5]
        path = OUT / f"receipt_{i + 1:02d}.png"
        render(store, date, items, subtotal, tax, total, card, path)
        manifest.append({
            "file": path.name, "store": store, "date": date.isoformat(),
            "items": [{k: it[k] for k in ("name", "category", "qty", "unit_price", "total")} for it in items],
            "subtotal": subtotal, "tax": tax, "total": total, "card_line": card,
        })
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"Wrote {WEEKS} receipts + manifest.json to {OUT}")
    # quick price-creep sanity line for the demo
    oat = [(m["date"], next(it["unit_price"] for it in m["items"] if it["name"].startswith("Oat Milk")))
           for m in manifest]
    print("Oat Milk price over time:", oat[0], "->", oat[-1],
          f"(+{round((oat[-1][1] - oat[0][1]) / oat[0][1] * 100)}%)")


if __name__ == "__main__":
    main()
