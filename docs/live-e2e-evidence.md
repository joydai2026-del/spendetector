# Spendetector live E2E evidence

The gate that actually matters (CLAUDE.md 3.13). Green unit tests are the floor, not proof.
Fill this in on the deployed build, from a real phone, before the Jun 12 demo. One row per run.

| Check | What to confirm | Done | Evidence (screenshot / note) |
|---|---|---|---|
| I1 | Snap a real receipt in the real bot -> reply in a few seconds with store/total/count + one insight + a tap link | [ ] | |
| I2 | Tapping the link opens the dashboard on the phone, with the just-scanned data | [ ] | |
| I3 | Items DB has one row per line item: correct Unit Price, Category from the 8, Norm Name populated | [ ] | |
| I4 | Re-send the SAME photo -> no duplicate Receipt/Item row, no duplicate reply | [ ] | |
| I5 | Full path works over CELLULAR (not home Wi-Fi), run twice with two different receipts | [ ] | |
| I6 | Pre-seeded real receipts make the donut + weekly bars + hero-item price line look alive; the advertised price-change % matches the real data | [ ] | |

## Latency (measure in rehearsal; the demo dead-air risk)
- Cold-container first scan: ____ s
- Warm-container scan (after a warm-up ping): ____ s
- Notes:

## Hero item (lock by Jun 8)
- Item: __________  Norm Name on the seeded rows: __________
- Real price gap: $______ (date) -> $______ (date) = ____%
