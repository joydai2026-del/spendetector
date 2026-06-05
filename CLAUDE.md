# Spendetector

> Snap a receipt, see what your bank can't: your real, itemized spending habits.
> Entry point for any Claude Code session in this repo. Global conventions live in `~/.claude/CLAUDE.md`.

## What this is
A cloud, phone-first personal app. Photograph a receipt in Telegram, an AI reads every line item, and a Notion dashboard reveals the spending habits and price changes a bank statement hides (it only shows the store total). This is JJ's **Notion community demo (Fri 2026-06-12)**.

## The problem it solves
Bank statements show "$87 at Target," never the items, so you never see your real habits. No budgeting app (Copilot, Rocket Money, Cleo) reads line items. Reward apps (Fetch) read them but sell your data. The gap: read your line items, keep the data yours, surface per-item price history (shrinkflation) and habits.

## Architecture (the loop)
`Telegram (photo)` → `Modal webhook (cloud, free tier)` → `GPT-4o vision → line-item JSON` → `Notion database + dashboard` → `bot replies with a tap-through Notion link`.

- **Capture:** a fresh dedicated Telegram bot via BotFather (locked 2026-06-04; reusing a personal bot is out because `setWebhook` makes a bot exclusive to one URL).
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

## Resolved decisions (office-hours 2026-06-04, locked in `.vault/plans/2026-06-04-spendetector-plan.md`)
- **Telegram bot:** a fresh dedicated bot (BotFather).
- **Notion home:** JJ's personal workspace, a fresh "Spendetector" page + databases (NOT the AI Collective business workspace `ntn` currently points at).
- **Categories:** a fixed canonical list the model classifies into (Groceries, Dining, Coffee, Snacks, Household, Health, Transport, Other); JJ recategorizes in Notion.
- **Card digits:** stripped and never stored (absent from the extraction schema; prompt forbids emitting them).
- **Bot reply:** one-shot (confirmation + one insight + tap-through link); no conversational Q&A for the demo. The `docs/plan.html` chat mockup's follow-up Q&A is out of demo scope.
- **Demo shape:** two beats (live itemization + seeded real-history price-creep), Notion dashboard is the on-screen hero. See the plan, sections 4 and 6.

## Non-negotiables
- **Cloud-first (Modal), phone-first.** Never Mac-tethered.
- **Notion is the star** (this is a Notion demo): the AI writes into a Notion database; Notion builds the dashboard.
- **Privacy:** never sell data; strip card digits; one-tap export/delete; OpenAI vision with retention/training opt-out.
- No hardcoding (env vars / config). Cut a branch before the first edit. No em dashes in output.

## Backup
Backed up to GitHub: **[joydai2026-del/spendetector](https://github.com/joydai2026-del/spendetector)** (private). `scripts/backup.sh` commits any uncommitted changes and pushes the current branch; a Claude Code **SessionEnd hook** runs it automatically, so every session's changes are backed up without anyone remembering to. `.env` and secrets are gitignored and never pushed. Run `bash scripts/backup.sh` anytime to back up on demand.
