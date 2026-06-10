import crypto from "node:crypto";
import { WebhookVerificationError, Worker } from "@notionhq/workers";

const worker = new Worker();
export default worker;

const NOTION_VERSION = "2022-06-28";
const OPENAI_MODEL = process.env.OPENAI_MODEL || "gpt-4o-2024-08-06";
const PRICE_MOVE_THRESHOLD = 0.1;

const CATEGORIES = [
  "Groceries",
  "Dining",
  "Coffee",
  "Snacks",
  "Household",
  "Health",
  "Transport",
  "Other",
] as const;

const FOOD_GROUP_ORDER = [
  "Produce",
  "Meat & Seafood",
  "Dairy & Eggs",
  "Bakery & Grains",
  "Pantry",
  "Snacks & Sweets",
  "Beverages",
  "Frozen",
  "Household",
  "Other",
] as const;

const HEALTH_TIERS = ["green", "yellow", "red"] as const;

type Item = {
  name: string;
  qty: number;
  unit_price: number | null;
  total: number | null;
  category: string;
  food_group: string;
  health_tier: string;
  confidence: number;
  norm_name: string;
};

type Receipt = {
  is_receipt: boolean;
  store: string | null;
  date: string | null;
  items: Item[];
  subtotal: number | null;
  tax: number | null;
  total: number | null;
};

type Insight = {
  text: string;
  kind: "price_move" | "biggest" | "cold_start";
};

type ReceiptReport = {
  headline: string;
  insights: string[];
  groups: Array<[string, Item[]]>;
  grade: string;
  group_percents: Array<[string, number]>;
  alert: string;
};

type Recipe = {
  name: string;
  minutes: number;
  uses: string[];
  steps: string;
};

function env(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

function notionToken(): string {
  const value = process.env.NOTION_API_TOKEN || process.env.SPENDETECTOR_NOTION_API_TOKEN;
  if (!value) {
    throw new Error("Missing required environment variable: NOTION_API_TOKEN");
  }
  return value;
}

function opt(name: string): string {
  return process.env[name] || "";
}

function verifyTelegramSecret(headers: Record<string, string>): void {
  const configured = env("TELEGRAM_WEBHOOK_SECRET");
  const actual = headers["x-telegram-bot-api-secret-token"];
  if (!actual || actual !== configured) {
    throw new WebhookVerificationError("Invalid Telegram webhook secret");
  }
}

function ownerOk(chatId: unknown): boolean {
  const allowed = opt("TELEGRAM_ALLOWED_CHAT_ID");
  if (allowed) {
    return String(chatId) === allowed;
  }
  return opt("SPENDETECTOR_ALLOW_INSECURE") === "1";
}

function largestPhotoFileId(message: any): string | null {
  const photos = message?.photo;
  if (Array.isArray(photos) && photos.length > 0) {
    return String(photos[photos.length - 1].file_id);
  }
  const doc = message?.document;
  if (doc?.file_id && String(doc.mime_type || "").startsWith("image/")) {
    return String(doc.file_id);
  }
  return null;
}

async function telegramApi(method: string, payload: Record<string, unknown>): Promise<any> {
  const response = await fetch(`https://api.telegram.org/bot${env("TELEGRAM_BOT_TOKEN")}/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`Telegram ${method} failed (${response.status})`);
  }
  return response.json();
}

async function sendMessage(chatId: string | number, text: string, parseMode = "HTML"): Promise<void> {
  await telegramApi("sendMessage", {
    chat_id: chatId,
    text,
    parse_mode: parseMode,
    disable_web_page_preview: true,
  });
}

async function getTelegramFileBytes(fileId: string): Promise<Buffer> {
  const meta = await telegramApi("getFile", { file_id: fileId });
  const path = meta?.result?.file_path;
  if (!path) {
    throw new Error("Telegram getFile returned no path");
  }
  const response = await fetch(`https://api.telegram.org/file/bot${env("TELEGRAM_BOT_TOKEN")}/${path}`);
  if (!response.ok) {
    throw new Error(`Telegram file download failed (${response.status})`);
  }
  return Buffer.from(await response.arrayBuffer());
}

function sha256(bytes: Buffer): string {
  return crypto.createHash("sha256").update(bytes).digest("hex");
}

function escapeHtml(text: string): string {
  return text.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

function link(label: string, url: string): string {
  if (!url) {
    return escapeHtml(label);
  }
  return `<a href="${url.replaceAll('"', "&quot;")}">${escapeHtml(label)}</a>`;
}

function greetingReply(): string {
  return "I'm Spendetector. Snap a photo of any receipt and I'll itemize it for you. Go ahead, send me one!";
}

function failedReply(): string {
  return "I could not read that one. Try a flatter, brighter photo.";
}

function nonReceiptReply(): string {
  return "Hmm, I could not read a receipt in that photo. Mind sending it again with the whole receipt in frame and the text facing up? Good light helps too.";
}

function errorReply(): string {
  return "Something hiccuped reading that receipt. Mind sending it again?";
}

function composeReply(receipt: Receipt, insight: Insight, receiptUrl: string | undefined, lowConf: number): string {
  const store = receipt.store || "Receipt";
  const head = receipt.total === null
    ? `${store}, ${receipt.items.length} items.`
    : `${store}, $${receipt.total.toFixed(2)}, ${receipt.items.length} items.`;
  const lines = [escapeHtml(head), escapeHtml(insight.text)];
  if (lowConf > 0) {
    lines.push(escapeHtml(`${lowConf} ${lowConf === 1 ? "item" : "items"} were unclear, tap to fix in Notion.`));
  }
  const url = receiptUrl || opt("SPENDETECTOR_DASHBOARD_URL");
  lines.push(link("See this receipt's report", url));
  return lines.join("\n");
}

const RECEIPT_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["is_receipt", "store", "date", "items", "subtotal", "tax", "total"],
  properties: {
    is_receipt: { type: "boolean" },
    store: { type: ["string", "null"] },
    date: { type: ["string", "null"], description: "purchase date as ISO YYYY-MM-DD" },
    items: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: [
          "name",
          "qty",
          "unit_price",
          "total",
          "category",
          "food_group",
          "health_tier",
          "confidence",
        ],
        properties: {
          name: { type: "string" },
          qty: { type: "number" },
          unit_price: { type: ["number", "null"] },
          total: { type: ["number", "null"] },
          category: { type: "string", enum: CATEGORIES },
          food_group: { type: "string", enum: FOOD_GROUP_ORDER },
          health_tier: { type: "string", enum: HEALTH_TIERS },
          confidence: { type: "number" },
        },
      },
    },
    subtotal: { type: ["number", "null"] },
    tax: { type: ["number", "null"] },
    total: { type: ["number", "null"] },
  },
};

const SYSTEM_PROMPT = [
  "You read retail receipts from a photo and return strict JSON.",
  `Classify each line item into exactly one of these categories: ${CATEGORIES.join(", ")}.`,
  "If unsure, use Other.",
  `Also tag each item with a food_group (one of: ${FOOD_GROUP_ORDER.join(", ")}) and a health_tier: green for whole/nutritious foods, yellow for neutral or processed staples, red for treats.`,
  "Non-food items are Household + yellow.",
  "NEVER output any card number, account number, or last-4 digits, ever.",
  "If only a line total is printed, set unit_price = total / qty.",
  "Output the purchase date as YYYY-MM-DD.",
  "Set confidence between 0 and 1 for how clearly you could read each item.",
  "If the image is not a receipt, set is_receipt to false and return an empty items list.",
].join(" ");

function toNumber(value: unknown): number | null {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function validIsoDate(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const d = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? null : value;
}

function scrubCard(text: string): string {
  return text
    .replace(/\d(?:[ -]?\d){11,18}/g, "####")
    .replace(/[*xX#]{2,}\s*\d{2,4}/g, "####");
}

function normalizeName(raw: string): string {
  return raw
    .toLowerCase()
    .replace(/\b\d+(?:\.\d+)?\s?(?:oz|ct|pk|lb|lbs|g|kg|ml|l|pack|x)\b/gi, " ")
    .replace(/[^a-z0-9 ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .split(" ")
    .slice(0, 3)
    .join(" ");
}

function coerceEnum(value: unknown, allowed: readonly string[], fallback: string): string {
  return typeof value === "string" && allowed.includes(value) ? value : fallback;
}

function toReceipt(data: any): Receipt {
  const items: Item[] = [];
  for (const raw of Array.isArray(data?.items) ? data.items : []) {
    if (!raw || typeof raw !== "object") {
      continue;
    }
    const name = scrubCard(String(raw.name || "Item")).trim() || "Item";
    const qty = toNumber(raw.qty) || 1;
    const total = toNumber(raw.total);
    let unitPrice = toNumber(raw.unit_price);
    if (unitPrice === null && total !== null && qty) {
      unitPrice = Math.round((total / qty) * 100) / 100;
    }
    items.push({
      name,
      qty,
      unit_price: unitPrice,
      total,
      category: coerceEnum(raw.category, CATEGORIES, "Other"),
      food_group: coerceEnum(raw.food_group, FOOD_GROUP_ORDER, "Other"),
      health_tier: coerceEnum(raw.health_tier, HEALTH_TIERS, "yellow"),
      confidence: toNumber(raw.confidence) ?? 1,
      norm_name: normalizeName(name),
    });
  }
  return {
    is_receipt: Boolean(data?.is_receipt ?? true),
    store: typeof data?.store === "string" ? scrubCard(data.store) : null,
    date: validIsoDate(data?.date),
    items,
    subtotal: toNumber(data?.subtotal),
    tax: toNumber(data?.tax),
    total: toNumber(data?.total),
  };
}

async function openAiJson(payload: Record<string, unknown>): Promise<any> {
  const response = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${env("OPENAI_API_KEY")}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`OpenAI chat failed (${response.status})`);
  }
  return response.json();
}

async function parseReceipt(imageBytes: Buffer): Promise<Receipt> {
  const b64 = imageBytes.toString("base64");
  const data = await openAiJson({
    model: OPENAI_MODEL,
    messages: [
      { role: "system", content: SYSTEM_PROMPT },
      {
        role: "user",
        content: [
          { type: "text", text: "Extract this receipt." },
          { type: "image_url", image_url: { url: `data:image/jpeg;base64,${b64}`, detail: "high" } },
        ],
      },
    ],
    response_format: {
      type: "json_schema",
      json_schema: { name: "receipt", strict: true, schema: RECEIPT_SCHEMA },
    },
    max_tokens: 2000,
    temperature: 0,
  });
  const content = data?.choices?.[0]?.message?.content;
  if (!content) {
    throw new Error("OpenAI returned an empty receipt parse");
  }
  return toReceipt(JSON.parse(content));
}

function select(name: string): any {
  const clean = name.replaceAll(",", " ").replace(/\s+/g, " ").trim().slice(0, 100) || "Unknown";
  return { select: { name: clean } };
}

function richText(value: string): any {
  return { rich_text: [{ text: { content: value.slice(0, 2000) } }] };
}

function setNumber(props: Record<string, any>, key: string, value: number | null): void {
  if (value !== null && Number.isFinite(value)) {
    props[key] = { number: value };
  }
}

function isoWeek(dateIso: string): string {
  const date = new Date(`${dateIso}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + 4 - (date.getUTCDay() || 7));
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  const weekNo = Math.ceil((((date.getTime() - yearStart.getTime()) / 86400000) + 1) / 7);
  return `${date.getUTCFullYear()}-W${String(weekNo).padStart(2, "0")}`;
}

function isoMonth(dateIso: string): string {
  return dateIso.slice(0, 7);
}

async function findReceiptByImageHash(notion: any, imageHash: string): Promise<boolean> {
  const response = await notionApi(`/databases/${env("SPENDETECTOR_RECEIPTS_DB_ID")}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
    filter: {
      and: [
        { property: "Image Hash", rich_text: { equals: imageHash } },
        { property: "Status", select: { does_not_equal: "failed" } },
      ],
    },
    page_size: 1,
    }),
  });
  return Boolean(response.results?.length);
}

async function findBaselinePrice(
  notion: any,
  normName: string,
  onOrBeforeIso: string,
): Promise<[number, string] | null> {
  try {
    const response = await notionApi(`/databases/${env("SPENDETECTOR_ITEMS_DB_ID")}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
      filter: {
        and: [
          { property: "Norm Name", select: { equals: normName } },
          { property: "Unit Price", number: { is_not_empty: true } },
          { property: "Date", date: { on_or_before: onOrBeforeIso } },
        ],
      },
      sorts: [{ property: "Date", direction: "ascending" }],
      page_size: 1,
      }),
    });
    const row = response.results?.[0];
    if (!row) {
      return null;
    }
    const props = row.properties || {};
    const price = props["Unit Price"]?.number;
    const date = props.Date?.date?.start;
    return typeof price === "number" && typeof date === "string" ? [price, date] : null;
  } catch (error: any) {
    if (error?.status === 400) {
      return null;
    }
    throw error;
  }
}

async function fetchPriorPrices(
  notion: any,
  items: Item[],
  onOrBeforeIso: string,
): Promise<Record<string, [number, string]>> {
  const out: Record<string, [number, string]> = {};
  for (const normName of new Set(items.map((item) => item.norm_name).filter(Boolean))) {
    const found = await findBaselinePrice(notion, normName, onOrBeforeIso);
    if (found) {
      out[normName] = found;
    }
  }
  return out;
}

function itemProps(item: Item, dateIso: string, receiptId: string, store: string | null): Record<string, any> {
  const props: Record<string, any> = {
    Item: { title: [{ text: { content: item.name } }] },
    Category: select(item.category),
    "Food Group": select(item.food_group),
    "Health Tier": select(item.health_tier),
    Date: { date: { start: dateIso } },
    Week: select(isoWeek(dateIso)),
    Month: select(isoMonth(dateIso)),
    Receipt: { relation: [{ id: receiptId }] },
  };
  if (item.norm_name) {
    props["Norm Name"] = select(item.norm_name);
  }
  if (store) {
    props.Store = select(store);
  }
  setNumber(props, "Qty", item.qty);
  setNumber(props, "Unit Price", item.unit_price);
  setNumber(props, "Line Total", item.total);
  return props;
}

async function writeReceipt(
  notion: any,
  receipt: Receipt,
  updateId: number,
  imageHash: string,
): Promise<{ receipt_id: string; url?: string; failed_items: number }> {
  const dateIso = receipt.date || new Date().toISOString().slice(0, 10);
  const title = `${receipt.store || "Receipt"} - ${dateIso}`;
  const props: Record<string, any> = {
    Title: { title: [{ text: { content: title } }] },
    Date: { date: { start: dateIso } },
    "Item Count": { number: receipt.items.length },
    "Telegram Update ID": { number: updateId },
    Status: select("complete"),
    "Image Hash": richText(imageHash),
  };
  if (receipt.store) {
    props.Store = select(receipt.store);
  }
  setNumber(props, "Subtotal", receipt.subtotal);
  setNumber(props, "Tax", receipt.tax);
  setNumber(props, "Total", receipt.total);

  const receiptPage = await notionApi("/pages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      parent: { database_id: env("SPENDETECTOR_RECEIPTS_DB_ID") },
      properties: props,
    }),
  });
  const receiptId = receiptPage.id;
  let failed = 0;

  for (const item of receipt.items) {
    try {
      await notionApi("/pages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          parent: { database_id: env("SPENDETECTOR_ITEMS_DB_ID") },
          properties: itemProps(item, dateIso, receiptId, receipt.store),
        }),
      });
    } catch {
      failed += 1;
    }
  }

  if (failed > 0) {
    const status = failed < receipt.items.length ? "partial" : "failed";
    await notionApi(`/pages/${receiptId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ properties: { Status: select(status) } }),
    });
  }

  return { receipt_id: receiptId, url: receiptPage.url, failed_items: failed };
}

function monthName(dateIso: string | null | undefined): string {
  if (!dateIso) {
    return "earlier";
  }
  const date = new Date(`${dateIso}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) {
    return "earlier";
  }
  return new Intl.DateTimeFormat("en-US", { month: "long", timeZone: "UTC" }).format(date);
}

function computeInsight(items: Item[], priorPrices: Record<string, [number, string]>): Insight {
  let best: { key: [number, number]; pct: number; item: Item; prior: number; priorDate: string } | null = null;
  for (const item of items) {
    const prior = priorPrices[item.norm_name];
    if (item.unit_price === null || !prior?.[0]) {
      continue;
    }
    const pct = (item.unit_price - prior[0]) / prior[0];
    if (Math.abs(pct) < PRICE_MOVE_THRESHOLD) {
      continue;
    }
    const key: [number, number] = [Math.abs(pct), item.total || 0];
    if (!best || key[0] > best.key[0] || (key[0] === best.key[0] && key[1] > best.key[1])) {
      best = { key, pct, item, prior: prior[0], priorDate: prior[1] };
    }
  }

  if (best) {
    const direction = best.pct > 0 ? "crept up" : "dropped";
    return {
      text: `Heads up: your ${best.item.norm_name} ${direction} ${Math.round(Math.abs(best.pct) * 100)}% since ${monthName(best.priorDate)}, from $${best.prior.toFixed(2)} to $${best.item.unit_price!.toFixed(2)}.`,
      kind: "price_move",
    };
  }

  if (Object.keys(priorPrices).length === 0) {
    return {
      text: "Saved. This is your first scan, so I am learning your prices now. Snap a few more and I will start spotting when things quietly go up.",
      kind: "cold_start",
    };
  }

  const priced = items.filter((item) => item.total !== null);
  if (priced.length > 0) {
    const biggest = priced.reduce((a, b) => (a.total! >= b.total! ? a : b));
    return { text: `Biggest item: ${biggest.name} at $${biggest.total!.toFixed(2)}.`, kind: "biggest" };
  }
  return { text: "Saved.", kind: "biggest" };
}

function grade(greenFraction: number): string {
  if (greenFraction >= 0.7) return "A";
  if (greenFraction >= 0.55) return "B";
  if (greenFraction >= 0.4) return "C";
  if (greenFraction >= 0.2) return "D";
  return "D";
}

function buildReceiptReport(receipt: Receipt, baselines: Record<string, [number, string]>): ReceiptReport {
  const total = receipt.items.reduce((sum, item) => sum + (item.total || 0), 0);
  const tiers = { green: 0, yellow: 0, red: 0 };
  const spendByGroup: Record<string, number> = {};
  const itemsByGroup: Record<string, Item[]> = {};

  for (const item of receipt.items) {
    const tier = item.health_tier in tiers ? item.health_tier as keyof typeof tiers : "yellow";
    tiers[tier] += 1;
    const group = FOOD_GROUP_ORDER.includes(item.food_group as any) ? item.food_group : "Other";
    spendByGroup[group] = (spendByGroup[group] || 0) + (item.total || 0);
    itemsByGroup[group] ||= [];
    itemsByGroup[group].push(item);
  }

  const healthGrade = grade(tiers.green / Math.max(receipt.items.length, 1));
  const groups: Array<[string, Item[]]> = FOOD_GROUP_ORDER
    .filter((group) => itemsByGroup[group])
    .map((group) => [group, itemsByGroup[group]]);

  const insights: string[] = [];
  insights.push(`Health score ${healthGrade}: ${tiers.green} of ${receipt.items.length} picks are whole foods${tiers.red ? `, ${tiers.red} treats.` : "."}`);

  const moves: Array<{ pct: number; item: Item; old: number; oldDate: string }> = [];
  for (const item of receipt.items) {
    const old = baselines[item.norm_name];
    if (item.unit_price === null || !old?.[0]) {
      continue;
    }
    const pct = (item.unit_price - old[0]) / old[0];
    if (Math.abs(pct) >= PRICE_MOVE_THRESHOLD) {
      moves.push({ pct, item, old: old[0], oldDate: old[1] });
    }
  }
  moves.sort((a, b) => Math.abs(b.pct) - Math.abs(a.pct));

  for (const move of moves.slice(0, 4)) {
    const word = move.pct > 0 ? "up" : "down";
    insights.push(`${move.item.norm_name} ${word} ${Math.round(Math.abs(move.pct) * 100)}% since ${monthName(move.oldDate)} ($${move.old.toFixed(2)} to $${move.item.unit_price!.toFixed(2)}).`);
  }

  const topGroups = Object.entries(spendByGroup).sort((a, b) => b[1] - a[1]).slice(0, 3);
  if (topGroups.length) {
    insights.push(`Where it went: ${topGroups.map(([g, v]) => `${g} $${v.toFixed(2)}`).join(", ")}`);
  }

  const priced = receipt.items.filter((item) => item.total !== null);
  const withUnit = receipt.items.filter((item) => item.unit_price !== null);
  if (priced.length && withUnit.length) {
    const splurge = priced.reduce((a, b) => (a.total! >= b.total! ? a : b));
    const value = withUnit.reduce((a, b) => (a.unit_price! <= b.unit_price! ? a : b));
    insights.push(`Best value: ${value.name} ($${value.unit_price!.toFixed(2)}). Splurge: ${splurge.name} ($${splurge.total!.toFixed(2)}).`);
  }

  const store = receipt.store || "the store";
  insights.push(`Your bank will just say "${store} $${total.toFixed(2)}." Now you know it was ${receipt.items.length} items across ${groups.length} food groups.`);

  const ups = moves.filter((move) => move.pct > 0);
  const headline = ups.length
    ? `Your ${ups[0].item.norm_name} jumped ${Math.round(ups[0].pct * 100)}% since ${monthName(ups[0].oldDate)}, and this haul scores ${healthGrade} for health.`
    : Object.keys(baselines).length === 0
      ? `First scan logged, health score ${healthGrade}. Snap a few more to unlock price tracking.`
      : `Logged ${receipt.items.length} items for $${total.toFixed(2)}. Health score ${healthGrade}, no big price jumps.`;

  const groupPercents = Object.entries(spendByGroup)
    .map(([g, v]) => [g, total ? (v / total) * 100 : 0] as [string, number])
    .sort((a, b) => b[1] - a[1]);

  const alert = ups.length
    ? `${ups[0].item.norm_name} up ${Math.round(ups[0].pct * 100)}% since ${monthName(ups[0].oldDate)}`
    : "";

  return { headline, insights, groups, grade: healthGrade, group_percents: groupPercents, alert };
}

const RECIPE_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["recipes"],
  properties: {
    recipes: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["name", "minutes", "uses", "steps"],
        properties: {
          name: { type: "string" },
          minutes: { type: "integer" },
          uses: { type: "array", items: { type: "string" } },
          steps: { type: "string" },
        },
      },
    },
  },
};

async function suggestRecipes(items: Item[]): Promise<Recipe[]> {
  const names = items.map((item) => item.name).filter(Boolean).slice(0, 25);
  if (!names.length) {
    return [];
  }
  try {
    const data = await openAiJson({
      model: OPENAI_MODEL,
      messages: [
        {
          role: "system",
          content: "You are a practical, friendly home cook. Given the items on a grocery receipt, suggest 2 to 3 easy recipes that use mainly those items. Assume salt, pepper, oil, water, and common spices are on hand.",
        },
        { role: "user", content: `Receipt items: ${names.join(", ")}` },
      ],
      response_format: {
        type: "json_schema",
        json_schema: { name: "recipes", strict: true, schema: RECIPE_SCHEMA },
      },
      max_tokens: 900,
      temperature: 0.4,
    });
    const parsed = JSON.parse(data.choices?.[0]?.message?.content || "{}");
    return (Array.isArray(parsed.recipes) ? parsed.recipes : []).slice(0, 3).map((recipe: any) => ({
      name: String(recipe.name || "Recipe"),
      minutes: Number(recipe.minutes || 20),
      uses: Array.isArray(recipe.uses) ? recipe.uses.map(String).slice(0, 8) : [],
      steps: String(recipe.steps || ""),
    }));
  } catch (error: any) {
    console.log(`recipe gen failed: ${error?.name || "Error"}: ${error?.message || error}`);
    return [];
  }
}

async function generateImage(prompt: string, size: string): Promise<Buffer | null> {
  try {
    const response = await fetch("https://api.openai.com/v1/images/generations", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${env("OPENAI_API_KEY")}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ model: "gpt-image-1", prompt, size, quality: "medium", n: 1 }),
    });
    if (!response.ok) {
      throw new Error(`OpenAI image failed (${response.status})`);
    }
    const data = await response.json();
    const b64 = data?.data?.[0]?.b64_json;
    return b64 ? Buffer.from(b64, "base64") : null;
  } catch (error: any) {
    console.log(`image gen failed: ${error?.name || "Error"}: ${error?.message || error}`);
    return null;
  }
}

function pantryPrompt(receipt: Receipt, report: ReceiptReport): string {
  const shelves = report.group_percents.slice(0, 6).map(([g, p]) => `${g} ${p.toFixed(0)}%`).join(", ") || "Groceries 100%";
  const alert = report.alert ? ` and '${report.alert}'` : "";
  return [
    "A cozy hand-drawn illustration of a grocery haul organized on warm wooden shelves like a tidy pantry.",
    "One shelf per food category, the items on each shelf drawn as cute simple icons.",
    `Each shelf has a small hand-lettered wooden sign showing the category name and percentage. Shelves: ${shelves}.`,
    `A small chalkboard in the corner reads 'Health: ${report.grade}'${alert}.`,
    `A header banner at the top reads '${receipt.store || "Groceries"} ${receipt.date || ""} $${(receipt.total || 0).toFixed(0)}'.`,
    "Warm wholesome storybook style, soft natural colors, clean legible labels, portrait orientation. No brand logos.",
  ].join(" ");
}

async function generateReportCard(receipt: Receipt, report: ReceiptReport): Promise<Buffer | null> {
  if (!receipt.items.length) {
    return null;
  }
  return generateImage(pantryPrompt(receipt, report), "1024x1536");
}

async function generateMenuImage(recipes: Recipe[]): Promise<Buffer | null> {
  const dishes = recipes.map((recipe) => recipe.name).slice(0, 3);
  if (!dishes.length) {
    return null;
  }
  return generateImage(
    `A cozy "Tonight's Menu" food illustration with ${dishes.length} appetizing plated dishes, each clearly labeled with its name: ${dishes.join(", ")}. Made from fresh groceries. Warm hand-drawn food-illustration style, soft colors, clean legible labels, portrait orientation.`,
    "1024x1536",
  );
}

async function notionApi(path: string, init: RequestInit): Promise<any> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${notionToken()}`);
  headers.set("Notion-Version", NOTION_VERSION);
  const response = await fetch(`https://api.notion.com/v1${path}`, { ...init, headers });
  const text = await response.text();
  if (!response.ok) {
    const error = new Error(`Notion API ${path} failed (${response.status}): ${text.slice(0, 500)}`) as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  return text ? JSON.parse(text) : {};
}

async function uploadImage(imageBytes: Buffer | null, filename: string): Promise<string | null> {
  if (!imageBytes) {
    return null;
  }
  try {
    const created = await notionApi("/file_uploads", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename, content_type: "image/png" }),
    });
    const arrayBuffer = imageBytes.buffer.slice(
      imageBytes.byteOffset,
      imageBytes.byteOffset + imageBytes.byteLength,
    ) as ArrayBuffer;
    const form = new FormData();
    form.append("file", new Blob([arrayBuffer], { type: "image/png" }), filename);
    await notionApi(`/file_uploads/${created.id}/send`, { method: "POST", body: form });
    return created.id;
  } catch (error: any) {
    console.log(`notion image upload failed: ${error?.name || "Error"}: ${error?.message || error}`);
    return null;
  }
}

function rich(content: string, url?: string): any[] {
  const text: any = { type: "text", text: { content: content.slice(0, 1900) } };
  if (url) {
    text.text.link = { url };
  }
  return [text];
}

function block(type: string, content: string, props: Record<string, any> = {}): any {
  return { object: "block", type, [type]: { rich_text: rich(content), ...props } };
}

function qtyStr(qty: number): string {
  return Number.isInteger(qty) ? String(qty) : String(qty);
}

async function appendReceiptReport(
  notion: any,
  pageId: string,
  receipt: Receipt,
  report: ReceiptReport,
  imageBytes: Buffer | null,
  recipes: Recipe[],
  menuImage: Buffer | null,
): Promise<void> {
  const children: any[] = [];
  const imageId = await uploadImage(imageBytes, "haul.png");
  if (imageId) {
    children.push({ object: "block", type: "image", image: { type: "file_upload", file_upload: { id: imageId } } });
  }

  children.push({
    object: "block",
    type: "callout",
    callout: {
      rich_text: rich(report.headline),
      icon: { type: "emoji", emoji: "\u{1F4A1}" },
      color: "blue_background",
    },
  });

  children.push(block("heading_2", "Insights for this receipt"));
  for (const line of report.insights.length ? report.insights : ["Nothing stood out on this one."]) {
    children.push(block("bulleted_list_item", line));
  }

  if (recipes.length) {
    children.push(block("heading_2", "Cook this tonight"));
    const menuId = await uploadImage(menuImage, "menu.png");
    if (menuId) {
      children.push({ object: "block", type: "image", image: { type: "file_upload", file_upload: { id: menuId } } });
    }
    for (const recipe of recipes) {
      children.push(block("heading_3", `${recipe.name} - ${recipe.minutes} min`));
      if (recipe.uses.length) {
        children.push(block("bulleted_list_item", `Uses: ${recipe.uses.join(", ")}`));
      }
      if (recipe.steps) {
        children.push(block("paragraph", recipe.steps));
      }
    }
  }

  children.push(block("heading_2", `What you bought (${receipt.items.length} items, $${(receipt.total || 0).toFixed(2)})`));
  for (const [groupName, groupItems] of report.groups) {
    children.push(block("heading_3", groupName));
    for (const item of groupItems) {
      const unit = item.unit_price === null ? "?" : `$${item.unit_price.toFixed(2)}`;
      const total = item.total === null ? "?" : `$${item.total.toFixed(2)}`;
      children.push(block("bulleted_list_item", `${item.name} - ${qtyStr(item.qty)} x ${unit} = ${total}`));
    }
  }

  const dashboard = opt("SPENDETECTOR_DASHBOARD_URL");
  if (dashboard) {
    children.push({
      object: "block",
      type: "paragraph",
      paragraph: { rich_text: rich("See your overall spending dashboard", dashboard) },
    });
  }

  await notionApi(`/blocks/${pageId}/children`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ children: children.slice(0, 100) }),
  });
}

async function buildAndAppendReport(
  notion: any,
  receiptId: string,
  receipt: Receipt,
  prior: Record<string, [number, string]>,
): Promise<void> {
  try {
    const report = buildReceiptReport(receipt, prior);
    const haul = await generateReportCard(receipt, report);
    const recipes = await suggestRecipes(receipt.items);
    const menu = recipes.length ? await generateMenuImage(recipes) : null;
    await appendReceiptReport(notion, receiptId, receipt, report, haul, recipes, menu);
  } catch (error: any) {
    console.log(`report build failed: ${error?.name || "Error"}: ${error?.message || error}`);
  }
}

async function handleTelegramUpdate(update: any, notion: any): Promise<Record<string, unknown>> {
  const updateId = Number(update?.update_id || 0);
  const message = update?.message || update?.edited_message || {};
  const chatId = message?.chat?.id;

  if (!ownerOk(chatId)) {
    return { status: "rejected", reason: "unauthorized_chat" };
  }

  const fileId = largestPhotoFileId(message);
  if (!fileId) {
    if (chatId !== undefined && chatId !== null) {
      await sendMessage(chatId, greetingReply());
    }
    return { status: "nudged", reason: "no_photo" };
  }

  try {
    const imageBytes = await getTelegramFileBytes(fileId);
    const imageHash = sha256(imageBytes);

    if (await findReceiptByImageHash(notion, imageHash)) {
      return { status: "duplicate" };
    }

    await sendMessage(chatId, "Got your receipt. Processing it now...");

    const receipt = await parseReceipt(imageBytes);
    if (!receipt.is_receipt) {
      await sendMessage(chatId, nonReceiptReply());
      return { status: "not_receipt" };
    }
    if (!receipt.items.length) {
      await sendMessage(chatId, failedReply());
      return { status: "empty" };
    }

    const effectiveDate = receipt.date || new Date().toISOString().slice(0, 10);
    const prior = await fetchPriorPrices(notion, receipt.items, effectiveDate);
    const insight = computeInsight(receipt.items, prior);
    const result = await writeReceipt(notion, receipt, updateId, imageHash);

    if (result.failed_items >= receipt.items.length) {
      await sendMessage(chatId, failedReply());
      return { status: "write_failed", receipt: result };
    }

    await buildAndAppendReport(notion, result.receipt_id, receipt, prior);
    const lowConf = receipt.items.filter((item) => (item.confidence ?? 1) < 0.5).length;
    await sendMessage(chatId, composeReply(receipt, insight, result.url, lowConf));
    return { status: "ok", insight_kind: insight.kind, receipt: result };
  } catch (error: any) {
    console.log(`worker heavy-path error: ${error?.name || "Error"}: ${error?.message || error}`);
    try {
      await sendMessage(chatId, errorReply());
    } catch (sendError: any) {
      console.log(`soft-fail send also failed: ${sendError?.name || "Error"}: ${sendError?.message || sendError}`);
    }
    return { status: "error", error: error?.name || "Error" };
  }
}

worker.webhook("telegramReceiptWebhook", {
  title: "Spendetector Telegram Receipt Webhook",
  description: "Receives Telegram receipt photos, extracts line items with GPT-4o, writes Notion rows, and replies with the receipt report link.",
  execute: async (events, { notion }) => {
    for (const event of events) {
      verifyTelegramSecret(event.headers);
      const result = await handleTelegramUpdate(event.body, notion);
      console.log("telegramReceiptWebhook:", JSON.stringify(result));
    }
  },
});
