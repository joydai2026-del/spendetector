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

## 2026-06-09 live result
- JJ tested the real end-to-end path with real receipt photos after the processing-ack deploy.
- Result: working end to end.
- Verified path: receipt photo in Telegram -> Modal webhook/worker -> GPT-4o extraction -> Notion rows/dashboard -> Telegram response.
- UX fix verified in same rehearsal: bot now sends an immediate processing acknowledgement before the final report.
- Remaining demo-day habit: run one smoke test the morning of the demo, ideally over cellular.

## 2026-06-09 Notion Worker route result
- Result: Worker route works end to end after the REST Notion API patch.
- Verified path: receipt photo in Telegram -> Notion Worker webhook -> GPT-4o extraction -> Notion Receipts DB + Items DB -> receipt report blocks/images -> Telegram response.
- Worker run: `019ead75-c548-779c-bdd4-bf18169b1899`, status `0`, started `2026-06-09T17:37:17.128Z`, completed `2026-06-09T17:38:51.723Z`.
- Worker log: `status: ok`, `insight_kind: price_move`, `failed_items: 0`.
- Notion evidence: new Trader Joe's receipt row for `$64.04`, created `2026-06-09T17:37:00.000Z`, URL `https://app.notion.com/p/Trader-Joe-s-2026-06-09-37a442f52cf7818f8988c1d70f882491`.
- Items evidence: line item rows created for Harvest Bread, TJ's Honey Nut O's Cereal, Sweet Italian Ckn Sausage, Ground Turkey, Hummus 7 oz, Beans Black, cilantro, sweet potatoes, Jazz apples, chicken breast, and others.
- Receipt page evidence: report blocks exist, including image, callout, `Insights for this receipt`, `Cook this tonight`, recipe blocks, and item detail blocks.
- Latency: about 95 seconds. Good enough for product proof, but risky for a live stage moment unless pre-warmed or narrated.

## Latency (measure in rehearsal; the demo dead-air risk)
- Cold-container first scan: ____ s
- Warm-container scan (after a warm-up ping): ____ s
- Notes:

## Hero item (lock by Jun 8)
- Item: Oat Milk  Norm Name on the seeded rows: oat milk
- Real price gap: $4.49 (2026-03-27) -> $5.65 (2026-06-04) = +26%

## Optional Watch button
- Status: not on the production dashboard.
- Reason: the backend endpoint exists, but the Notion UI button is not configured and live-tested yet.
- Required before showing it: deploy `notion_watch_webhook`, configure Notion `Send webhook`, add `X-Spendetector-Notion-Secret`, run one real button click, and verify the Watchlist row appears.
