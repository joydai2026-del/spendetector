"""Run the 10 test receipts through the REAL pipeline: GPT-4o extract -> Notion write.

This verifies extraction accuracy against the manifest ground truth and seeds the Notion
databases so the dashboard has data. It exercises extract.py + notion_io.py against the live
APIs, but NOT the Telegram/Modal webhook path (do that with one real send from the phone).

    set -a; . ./.env; set +a
    .venv/bin/python scripts/seed_from_receipts.py
"""

from __future__ import annotations

import hashlib
import json
import pathlib

from spendetector import extract, notion_io

OUT = pathlib.Path(__file__).resolve().parent.parent / "testdata" / "receipts"


def main() -> None:
    manifest = {m["file"]: m for m in json.loads((OUT / "manifest.json").read_text())}
    oat_series = []
    leaks = 0
    for n, png in enumerate(sorted(OUT.glob("receipt_*.png")), start=900001):
        data = png.read_bytes()
        receipt = extract.parse_receipt(data)
        image_hash = hashlib.sha256(data).hexdigest()
        res = notion_io.write_receipt(receipt, update_id=n, image_hash=image_hash)
        gt = manifest[png.name]

        # card-scrub check: no fake card tail may survive into any written field
        for tail in ("4821", "7193"):
            if (receipt.store and tail in receipt.store) or any(tail in it.name for it in receipt.items):
                leaks += 1
                print(f"  !! LEAK: card tail {tail} in {png.name}")

        oat = next((it.unit_price for it in receipt.items if it.norm_name == "oat milk"), None)
        if oat is not None:
            oat_series.append((receipt.date, oat))
        print(f"{png.name}: store={receipt.store!r} date={receipt.date} "
              f"items={len(receipt.items)}/{len(gt['items'])} total={receipt.total} (gt {gt['total']}) "
              f"failed_items={res['failed_items']}")

    print("\nOat-milk unit price as extracted (the demo's price-creep series):")
    for d, p in oat_series:
        print(f"  {d}: ${p}")
    print(f"\ncard leaks: {leaks} (must be 0)")


if __name__ == "__main__":
    main()
