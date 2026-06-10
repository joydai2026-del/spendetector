#!/usr/bin/env bash
# One-time deploy: build the Modal secret from .env, deploy the app, register the Telegram
# webhook. Run this AFTER .env is filled and `python -m spendetector.setup_notion` has produced
# the two database ids. Safe to re-run (it overwrites the secret and redeploys).
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env ] || { echo "No .env found. Copy .env.example to .env and fill it in first."; exit 1; }
set -a; . ./.env; set +a

: "${TELEGRAM_BOT_TOKEN:?set in .env}"
: "${TELEGRAM_WEBHOOK_SECRET:?set in .env}"
: "${SPENDETECTOR_ITEMS_DB_ID:?run python -m spendetector.setup_notion first}"

modal profile activate mengzxapp

# (Re)create the Modal secret from the current .env values.
modal secret create spendetector-secrets \
  TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" \
  TELEGRAM_WEBHOOK_SECRET="$TELEGRAM_WEBHOOK_SECRET" \
  TELEGRAM_ALLOWED_CHAT_ID="$TELEGRAM_ALLOWED_CHAT_ID" \
  OPENAI_API_KEY="$OPENAI_API_KEY" \
  NOTION_TOKEN="$NOTION_TOKEN" \
  SPENDETECTOR_RECEIPTS_DB_ID="$SPENDETECTOR_RECEIPTS_DB_ID" \
  SPENDETECTOR_ITEMS_DB_ID="$SPENDETECTOR_ITEMS_DB_ID" \
  NOTION_DASHBOARD_URL="$NOTION_DASHBOARD_URL" \
  ${SPENDETECTOR_WATCHLIST_DB_ID:+SPENDETECTOR_WATCHLIST_DB_ID="$SPENDETECTOR_WATCHLIST_DB_ID"} \
  ${NOTION_WORKER_SECRET:+NOTION_WORKER_SECRET="$NOTION_WORKER_SECRET"} \
  ${NOTION_PRICE_VIEW_URL:+NOTION_PRICE_VIEW_URL="$NOTION_PRICE_VIEW_URL"} \
  --force

echo "Deploying to Modal..."
modal deploy spendetector/app.py | tee /tmp/spendetector-deploy.log
URL="$(grep -oE 'https://[^ ]+telegram-webhook[^ ]*\.modal\.run' /tmp/spendetector-deploy.log | head -1)"

if [ -z "$URL" ]; then
  echo "Could not auto-detect the webhook URL from the deploy output."
  echo "Find it in the Modal output above, then run:"
  echo "  curl \"https://api.telegram.org/bot\$TELEGRAM_BOT_TOKEN/setWebhook\" -d url=<URL> -d secret_token=\$TELEGRAM_WEBHOOK_SECRET"
  exit 1
fi

echo "Registering Telegram webhook: $URL"
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d "url=${URL}" -d "secret_token=${TELEGRAM_WEBHOOK_SECRET}" | python3 -m json.tool

echo
echo "Done. Send a receipt photo to your bot and watch the row appear in Notion."
