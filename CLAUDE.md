# Spendetector

> Snap a receipt, see what your bank can't: your real, itemized spending habits.
> Entry point for any Claude Code session in this repo. Global conventions live in `~/.claude/CLAUDE.md`.

## What this is
A cloud, phone-first personal app. Photograph a receipt in Telegram, an AI reads every line item, and a Notion dashboard reveals the spending habits and price changes a bank statement hides (it only shows the store total). This is JJ's **Notion community demo (Fri 2026-06-12)**.

## The problem it solves
Bank statements show "$87 at Target," never the items, so you never see your real habits. No budgeting app (Copilot, Rocket Money, Cleo) reads line items. Reward apps (Fetch) read them but sell your data. The gap: read your line items, keep the data yours, surface per-item price history (shrinkflation) and habits.

## Architecture (the loop)
`Telegram (photo)` → `Modal webhook (cloud, free tier)` → `GPT-4o vision → line-item JSON` → `Notion database + dashboard` → `bot replies with a tap-through Notion link`.

- **Capture:** Telegram bot (reuse JJ's personal bot, or a fresh one).
- **Cloud:** Modal (serverless; Modal ships an official receipt-OCR example to start from). Never the Mac.
- **Extraction:** GPT-4o vision, strict JSON `{store, date, items[{name, qty, unit_price, total}], tax, total}`. ~90% line-item accuracy, ~$0.005/receipt. Use full GPT-4o, NOT mini (mini's image-token quirk erases the savings).
- **Store + charts:** Notion API (free). Notion charts read plain number/select fields the bot writes (charts cannot use formulas or rollups on an axis).
- **Cost:** ~$0 to $10 / month total.

## The plan
Full plan with diagrams, dashboard mockups, and the demo script: **`docs/plan.html`** (open in a browser). Decision record: `~/Documents/jj-knowledge-vault/agents/claude-code-m4/decisions/2026-06-04-notion-personal-products.md`.

## How to build
1. `/memory-loader` (session start, mandatory).
2. `/planning-pipeline` (office-hours → CEO → eng → design → success-criteria) **before any code**.
3. Build with Claude Code on a `feat/` branch; Codex + context-free review gate per change.
4. QA the real end-to-end (snap a real receipt → row appears in Notion → link back to phone), not just unit tests.

## Open decisions (resolve in office-hours)
- Telegram bot: reuse JJ's personal bot token, or a fresh one?
- Which personal Notion page hosts the Spending dashboard (share it with the integration)?
- Category list (groceries / dining / coffee / household / ...), or model-inferred + JJ corrects?
- Confirm: strip and never store card digits.

## Non-negotiables
- **Cloud-first (Modal), phone-first.** Never Mac-tethered.
- **Notion is the star** (this is a Notion demo): the AI writes into a Notion database; Notion builds the dashboard.
- **Privacy:** never sell data; strip card digits; one-tap export/delete; OpenAI vision with retention/training opt-out.
- No hardcoding (env vars / config). Cut a branch before the first edit. No em dashes in output.
