# Spendetector demo playbook

## Brutal positioning

This is strongest when it is framed as a Notion-native product, not as a receipt OCR script.

The audience should leave with one sentence:

> My bank saw store totals. Notion became the product layer for item-level spending intelligence.

## Demo order

1. Open Notion first. Do not start in Telegram.
2. Show the hero: oat milk is up 26%.
3. Say the plain contrast: "My bank saw Whole Foods totals. Spendetector saw 221 items."
4. Send one real receipt photo in Telegram.
5. While it processes, point at the Notion sections that are powered by the same Items DB.
6. Show the new receipt or bot reply link.
7. Optional, only if configured and live-tested: show a Notion button triggering the worker.

## What Notion does

| Product job | Notion role |
|---|---|
| Frontend | The dashboard is the user-facing app. |
| Database | Receipts DB stores each receipt. Items DB stores each line item. |
| Dashboard | Native chart views show monthly spend, price history, food groups, health mix, and weekly spend. |
| Editor | JJ can fix item categories and names directly in Notion. |
| Control panel | A button or database automation can send a webhook to Modal. |

## What the worker does

| Worker job | Why Notion should not do it alone |
|---|---|
| Download Telegram image | Notion does not receive Telegram photos directly. |
| Call GPT-4o vision | Notion is not the OCR engine here. |
| Normalize line items | Needed for stable price history. |
| Compute price movement | Cross-row historical comparisons are easier and safer in code. |
| Write chart-friendly fields | Notion charts need plain number, select, and date fields. |
| Generate receipt report extras | GPT image creates the fun visual report card; GPT-4o suggests menu ideas from the actual items. |
| Handle watchlist webhooks | Notion sends the trigger; Modal verifies and computes. |

## AI report extras

Spendetector uses two AI layers after the receipt is parsed:

| Layer | What it does | Where it appears |
|---|---|---|
| GPT-4o vision | Reads the receipt photo and returns structured JSON. | Notion Receipts and Items databases. |
| GPT image | Generates a fun visual report card for the receipt, such as a cozy pantry-style illustration of the haul. | The per-receipt Notion report page. |
| GPT-4o text | Suggests practical menu ideas using the actual receipt items. | The per-receipt Notion report page. |

Presenter line:

"The first AI job is serious: read the receipt accurately. The second AI job is delightful: turn the receipt into a little report card with health signals and meal ideas, so the data feels usable instead of like a spreadsheet."

## Watch another item (future or optional live-tested feature)

Do not show this on the production dashboard until the button exists in Notion and has been tested end to end.

Best version when ready:

1. Show the Notion button in the real dashboard.
2. Click it once.
3. Show the new or refreshed Watchlist row.
4. Say: "A Notion button sends the item name to the Modal worker. The worker computes first price, latest price, and change percent, then writes the result back to Notion."

Good candidate Watchlist rows:

| Item | Baseline | Latest | Change |
|---|---:|---:|---:|
| Oat Milk | $4.49 | $5.65 | +26% |
| Eggs Large Dozen | $3.99 | $6.16 | +54% |
| Chicken Breast | $5.99 | $7.43 | +24% |
| Greek Yogurt | $5.49 | $6.21 | +13% |

Button setup shape:

| Step | Setting |
|---|---|
| Notion action | Send webhook |
| Method | POST |
| URL | Modal `notion_watch_webhook` URL |
| Header | `X-Spendetector-Notion-Secret` |
| Payload | `{"norm_name": "oat milk"}` or selected database properties |

Security caveat: Notion webhook actions do not authenticate by default. The Modal endpoint must reject missing or wrong `X-Spendetector-Notion-Secret`.

## Notion Agent answer

It is fine that this demo does not depend on a custom Notion Agent.

Why:

1. This is a stronger deterministic demo. The live receipt path does not rely on an agent deciding what to do.
2. Notion Agent is better as a future assistant over the workspace, not the core ingestion path.
3. Current Notion Agent docs say it cannot create advanced properties like formulas, rollups, buttons, automations, or database templates by itself.

How to mention it:

"Today, Notion is the product layer: database, dashboard, editor, and control panel. A Notion Agent could become the assistant over this later, asking questions like 'what got more expensive this month?' or drafting weekly summaries, but the core product works without relying on a probabilistic agent."

## Future product ideas

| Feature | Why it is good |
|---|---|
| Price Watch leaderboard | Clear wow, easy to understand. |
| Watch another item button | Makes Notion feel interactive, but only after the button is actually configured and tested. |
| Correction memory | If JJ fixes a category, future receipts should learn it. |
| Store comparison | "Oat milk is cheaper at Trader Joe's than Whole Foods." |
| Weekly Notion recap | Native Notion page generated each week. |
| Shopping list | Repeated staples become a suggested list. |
| Privacy controls | Export and delete buttons make the data ownership story real. |
| Meal ideas | Uses receipt contents to suggest dinner, but keep it secondary. |

## Presenter lines

"Most budgeting apps categorize the transaction. This categorizes the receipt."

"A bank statement has one row. Notion gives me the product surface: charts, gallery, calendar, editable data, and automations."

"The AI is not the app. The AI reads the receipt. Notion is where the product lives."

"This is why I like Notion for AI products: it gives you a database, dashboard, editor, and workflow surface before you build a custom frontend."

"Modal runs the processing. It does not store my spending history. The durable product data lives in my private Notion workspace."
