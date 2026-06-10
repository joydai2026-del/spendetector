# Spendetector Notion Worker Trial

This branch tries the same receipt loop without Modal:

`Telegram photo -> Notion Worker webhook -> GPT-4o -> Notion Receipts/Items DBs -> Telegram reply`

The Modal branch is still the proven demo path until this Worker passes a real receipt test.

## Why this exists

Notion Workers can run deterministic TypeScript code inside Notion's hosted runtime. For the demo, this is a strong answer to: "Can Notion do this without Modal?"

Answer: yes, in principle. The Worker can receive the Telegram webhook, call external APIs, write to Notion, and act as the runtime. It is different from a Notion Custom Agent. Custom Agents are an AI interface; Workers are code.

## Secrets

Set these on the Worker before deploying:

```bash
ntn workers env set \
  TELEGRAM_BOT_TOKEN=... \
  TELEGRAM_WEBHOOK_SECRET=... \
  TELEGRAM_ALLOWED_CHAT_ID=... \
  OPENAI_API_KEY=... \
  NOTION_API_TOKEN=... \
  SPENDETECTOR_RECEIPTS_DB_ID=... \
  SPENDETECTOR_ITEMS_DB_ID=... \
  SPENDETECTOR_DASHBOARD_URL=...
```

`NOTION_API_TOKEN` should be the same Notion integration token the Python app currently calls `NOTION_TOKEN`. Notion Workers require this exact name for `context.notion`. Other `NOTION_` names are reserved, so the dashboard URL uses `SPENDETECTOR_DASHBOARD_URL`.

Optional:

```bash
ntn workers env set OPENAI_MODEL=gpt-4o-2024-08-06
```

## Deploy

```bash
cd notion-worker
npm install
ntn login
ntn workers deploy --name spendetector-worker
ntn workers webhooks list
```

Live deployment, 2026-06-09:

```text
Worker ID: 019ead5b-3331-7fc0-86e4-760f74832232
Webhook: telegramReceiptWebhook
```

`ntn` is logged into `JD's Workspace` as `joyd.nb2024@gmail.com`, and `ntn doctor` now reports both Workers API and public API auth as passing.

Live evidence:

- `ntn workers deploy` updates the Worker successfully from this folder.
- `ntn workers env set` has the required runtime secrets configured.
- Telegram `getWebhookInfo` points to the Notion Worker URL with zero pending updates and no delivery error.
- A controlled direct webhook test returned a Notion event id and produced a successful `webhook:telegramReceiptWebhook` run with `status: nudged`, `reason: no_photo`.
- Real receipt E2E passed after the REST Notion API patch. Run `019ead75-c548-779c-bdd4-bf18169b1899` returned `status: ok`, `insight_kind: price_move`, `failed_items: 0`.
- Verified Notion output: new Trader Joe's receipt row for `$64.04`, item rows, report blocks, recipe blocks, and generated images on the receipt page.

If `workers.json` already exists, update the Worker with `ntn workers deploy` without `--name`.

Take the `telegramReceiptWebhook` URL and set it as the Telegram webhook:

```bash
curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
  -d "url=$NOTION_WORKER_WEBHOOK_URL" \
  -d "secret_token=$TELEGRAM_WEBHOOK_SECRET"
```

## Test

Send a real receipt photo to the Telegram bot.

Expected behavior:

1. Telegram gets an immediate "Got your receipt" message once the Worker starts.
2. GPT-4o extracts structured receipt JSON.
3. Notion gets one receipt row and one item row per line item.
4. The receipt page gets the health report, recipe ideas, and best-effort GPT images.
5. Telegram gets the final tap-through Notion link.

Latest measured Worker run time: about 95 seconds for the full OCR, Notion writes, report generation, image generation, and Telegram reply path. For a live demo, pre-warm and keep a backup receipt ready.

## Important differences from Modal

- Notion returns `202 Accepted` to Telegram before the Worker finishes. The Telegram acknowledgement is still a bot message, but it happens after Notion starts the queued run.
- There is no `modal.Dict` update-id cache. This Worker uses the durable image hash guard in the Receipts DB.
- Worker run logs are checked with `ntn workers runs list` and `ntn workers runs logs <run-id>`.
