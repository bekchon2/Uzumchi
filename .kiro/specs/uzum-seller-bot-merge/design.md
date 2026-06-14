# Uzum Seller Bot Merge — Bugfix Design

## Overview

The Uzumchi bot is the base codebase that this fix lands in. Relative to the reference
bot (`uzum_seller_bot`), Uzumchi is the more advanced of the two (multi-shop, Gemini AI
advisor, competitor monitoring, SKU-variant display) but it is missing or misbehaving on
five behaviors that sellers depend on. This design treats those five gaps as a single
composite bug condition `C(X)` made of independent sub-conditions, and specifies an
**additive, minimal-change** fix that leaves Uzumchi's advanced features untouched.

**Scope guardrail:** every change in this design targets files inside
`/projects/sandbox/Uzumchi` only. The reference repository `/projects/sandbox/uzum_seller_bot`
is read-only — it is consulted for behavior to port (self-ping loop, finance-order parsing,
delivered-notification text) but MUST NOT be edited.

The fix strategy is deliberately **additive**:

1. **i18n centralization** — move scheduler + report-handler user-facing strings into the
   existing `locales/i18n.py` `t()` catalog by adding new keys (uz + ru). The `t()` function
   signature and all existing keys stay unchanged.
2. **Self-ping keep-alive** — add a background coroutine in `Uzumchi/main.py` that pings its
   own `/ping` when `RENDER_EXTERNAL_URL` is set, and no-ops (logs and returns) locally.
3. **Detailed commission/profit reporting** — add finance-order parsing/aggregation as **new**
   functions in `services/uzum_api.py` (no change to existing contracts) and wire the new
   aggregate into Orders, daily, weekly, and monthly reports, including profit-margin %.
4. **`ms_to_date` defect avoidance** — when porting the delivered-order date display, use a
   date-formatting helper that is correctly defined **and** imported in Uzumchi
   (`utils/helpers.format_date`), so no `NameError` is introduced.
5. **Data-layer reconciliation** — keep `get_products` (raw list), `get_finance_orders`
   (Uzumchi signature), `parse_invoices`→`StorageItem`, `summarize_orders`, and
   `get_storage_alerts` exactly as they are; finance reporting is layered on top as new code
   so the AI advisor, competitor monitor, multi-shop, and SKU-variant features keep their
   data shapes.

## Glossary

- **Bug_Condition (C)**: The union of runtime/code situations that trigger any of the five
  defects — inline-string rendering in scheduler/report handlers, absence of a Render
  keep-alive loop, omission of commission/profit/logistics/margin in reports, a ported
  `ms_to_date` NameError, and data-shape divergence between the two bots' data layers.
- **Property (P)**: The desired post-fix behavior — strings flow through `t()`, the service
  is kept awake on Render, reports include finance detail, the delivered-check job runs to
  completion, and existing data shapes are preserved.
- **Preservation**: Existing Uzumchi behavior that MUST remain byte-for-byte equivalent —
  the Gemini advisor, competitor monitor, multi-shop switching, SKU-variant display, charts,
  storage tracking, `/ping` + `/health`, the products-fallback path, and the existing helpers.
- **`t(key, lang, **kwargs)`**: the central translation accessor in `locales/i18n.py`; reads
  from the `TEXTS` dict, falls back to `ru` then to `[key]`, and `.format(**kwargs)` is
  swallow-on-error. Unchanged by this fix.
- **`summarize_orders(orders)`**: Uzumchi aggregator returning
  `{total, delivered, cancelled, processing, shipped, revenue}` from heterogeneous order
  dicts. The AI advisor depends on this shape. Unchanged.
- **`get_products(api_key, shop_id)`**: Uzumchi data-layer call returning a **raw `list[dict]`**
  of products (each with `skuList`). Consumed directly (`.get("skuList")`, `calc_total_qty`,
  `format_product_skus`) by products view, storage view, AI advisor, and competitor matching.
  Unchanged.
- **`get_finance_orders(api_key, date_from, date_to, limit, offset)`**: Uzumchi data-layer
  call returning the **raw dict** from `/v1/finance/orders`. Its signature is preserved; new
  parse/extract helpers consume its output.
- **`parse_invoices(invoices) -> list[StorageItem]`** / **`get_storage_alerts(items)`**: the
  storage data layer in `services/storage_tracker.py`. Unchanged.
- **Finance order**: an item from `/v1/finance/orders` exposing `sellPrice`, `commission`,
  `sellerProfit`, `logisticDeliveryFee`, `dateIssued`, `skuTitle`, `productTitle`.
- **Profit margin (rentabellik)**: `seller_profit_total / revenue_total * 100`, shown as a `%`.

## Bug Details

### Bug Condition

The bug manifests in five independent situations. `isBugCondition` returns true if **any**
sub-condition holds. Each sub-condition maps to a `bugfix.md` "Current Behavior" clause.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input — a runtime event of one of these kinds:
         { kind: "render_text",  surface, lang }              // scheduler/report rendering
         { kind: "render_idle",  render_external_url }        // platform idle window
         { kind: "open_report",  report in {orders, daily, weekly, monthly} }
         { kind: "delivered_notify", date_issued_ms }         // delivered-check job
         { kind: "data_consumer", feature, contract }         // AI/competitor/multishop/sku
  OUTPUT: boolean

  // 1.1 — inline strings instead of central catalog
  IF input.kind == "render_text"
       AND input.surface IN { morning_report, storage_alert, delivered, orders,
                              storage_view, today_report, weekly_report, monthly_report }
       AND stringsBuiltFromInlineIfElse(input.surface)        // not via t()
     RETURN true

  // 1.2 — no self-ping keep-alive
  IF input.kind == "render_idle"
       AND noSelfPingTaskRegistered()
     RETURN true

  // 1.3/1.4/1.5 — finance detail missing from reports
  IF input.kind == "open_report"
       AND financeDataAvailable()
       AND reportOmits(input.report, { commission, sellerProfit, logistics, marginPct })
     RETURN true

  // 1.6 — ported ms_to_date NameError
  IF input.kind == "delivered_notify"
       AND usesUndefinedDateHelper()                          // ms_to_date not defined/imported
     RETURN true

  // 1.7 — data-shape divergence breaks consumers
  IF input.kind == "data_consumer"
       AND mergeChangedContract(input.contract)               // get_products/get_finance_orders/parse_invoices/summarize_orders
     RETURN true

  RETURN false
END FUNCTION
```

### Examples

- **1.1 (inline strings):** `run_morning_reports` in `services/scheduler.py` builds the
  morning report from a hardcoded `if lang == "uz": ... else: ...` block; the equivalent
  Russian/Uzbek copy also lives inline in `handlers/analytics.py` (`cmd_weekly`,
  `cmd_monthly`) and `handlers/main_menu.py` (`cmd_orders`, `cmd_report_today`) — duplicated
  and drift-prone. _Expected:_ each string comes from `t("...", lang, ...)`.
- **1.2 (idle):** On Render free tier with no inbound traffic for the idle window and no
  self-ping task, the web service spins down and the APScheduler jobs + polling stop.
  _Expected:_ a background loop pings `{RENDER_EXTERNAL_URL}/ping` periodically.
- **1.3 (orders/daily):** `cmd_orders` and `cmd_report_today` show only
  `total/delivered/cancelled/revenue` from `summarize_orders`; net profit, commission, and
  logistics never appear. _Expected:_ per-order commission and seller profit are shown when
  finance data is available.
- **1.4 (weekly):** `cmd_weekly` shows counts + revenue + a daily bar chart only — no
  commission, logistics, net profit, or margin %. _Expected:_ aggregate commission,
  logistics, net profit, and margin % alongside revenue.
- **1.5 (monthly):** `cmd_monthly` derives `total_expenses` from `get_expenses` only and
  computes a coarse profit; it omits per-order commission/seller-profit/logistics.
  _Expected:_ aggregates computed from per-order finance fields, including margin %.
- **1.6 (NameError):** The reference `check_delivered_orders` calls
  `ms_to_date(o['date_issued'])` while importing only `ms_to_date_str` — a `NameError` if
  copied verbatim. _Expected (edge case):_ Uzumchi formats the received date via
  `utils/helpers.format_date`, which is defined and imported, so the job completes.
- **1.7 (data divergence):** The reference `get_products` returns a dict consumed via
  `extract_products`/`parse_product`, and its `get_finance_orders(api_key, shop_id, ...)`
  takes `shop_id` positionally — both differ from Uzumchi. A naive copy-over would change
  the list/dict shape that `format_product_skus`, the AI advisor, and competitor matching
  rely on. _Expected:_ Uzumchi contracts are preserved; finance parsing is added as new code.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors (must keep working exactly as today):**
- Gemini AI advisor in `services/gemini_ai.py` — `ask_gemini`, `build_sales_analysis_prompt`,
  `build_storage_advice_prompt`, `build_competitor_advice_prompt` — keeps consuming
  `get_products` (raw list), `summarize_orders` (dict), and `parse_invoices` (`StorageItem`).
- Competitor monitor in `services/competitor_monitor.py` — URL→id extraction, HTML title
  fetch, API price fetch, the `product_urls` / `competitor_tracking` tables, and both report
  renderers (`check_saved_urls`, `format_single_product_report`).
- Multi-shop: `set_active_shop`, `shop_ids`, `active_shop_id`, and shop switching during
  onboarding and from settings.
- SKU-variant display: `format_product_skus` and `_get_sku_variant_name` in
  `services/uzum_api.py`.
- Charts: `weekly_sales_chart`, `monthly_sales_chart`, `stock_pie_chart` in
  `services/charts.py`.
- Storage data layer: `parse_invoices`→`StorageItem` and `get_storage_alerts`.
- Web endpoints `/ping` and `/health` respond successfully as today.
- Orders fallback: `get_sales_stats_from_products` when the orders API returns 403.
- Helpers `stock_icon`, `safe_float`, `safe_int`, `short_name` keep their names and behavior.

**Scope:**
All inputs that do NOT match a sub-condition of `isBugCondition` must be completely
unaffected. In particular:
- Any caller of `get_products`, `summarize_orders`, `parse_invoices`, `get_storage_alerts`,
  or `get_finance_orders` receives the same return shape as before the fix.
- Any existing `t()` key continues to resolve to the same string.
- A request to `/ping` or `/health` returns the same response as today.

_(The expected correct behavior for buggy inputs is defined in the Correctness Properties
section; this section enumerates what must NOT change.)_

## Hypothesized Root Cause

1. **Divergent evolution, not regression.** Uzumchi and `uzum_seller_bot` were forked and
   evolved separately; Uzumchi gained advanced features but never absorbed the reference
   bot's finance reporting, self-ping, and i18n discipline. The "bugs" are missing ports and
   inconsistent string handling rather than a single broken line.

2. **i18n drift (1.1).** Scheduler jobs and report handlers were written with inline
   `if lang == "uz"` blocks for speed; the central catalog exists and is used elsewhere, so
   the cause is incomplete adoption, not a broken `t()`.

3. **Missing keep-alive (1.2).** `Uzumchi/main.py` never imported `aiohttp` as a client, never
   read `RENDER_EXTERNAL_URL`, and never scheduled a background ping task.

4. **Reporting depth gap (1.3/1.4/1.5).** Reports are built only from `summarize_orders`
   (counts + gross revenue) and a coarse `get_expenses` total; the per-order finance fields
   (`commission`, `sellerProfit`, `logisticDeliveryFee`) from `/v1/finance/orders` are fetched
   by `get_finance_orders` but never parsed or aggregated.

5. **Latent NameError on port (1.6).** The reference `check_delivered_orders` references
   `ms_to_date` but imports only `ms_to_date_str`; copying it verbatim into Uzumchi would
   raise `NameError`. Uzumchi already has an equivalent correct helper, `format_date(ts_ms)`.

6. **Contract mismatch (1.7).** The two bots' `get_products` and `get_finance_orders` have
   different return shapes and signatures; a naive merge that pulls in
   `extract_products`/`parse_product` would silently change the shape Uzumchi consumers expect.

## Correctness Properties

Property 1: Bug Condition — Centralized i18n for scheduler and report strings

_For any_ scheduler job or report handler rendering a user-facing string where the bug
condition holds (string currently built from an inline `if lang` block), the fixed code
SHALL obtain that string from `locales/i18n.py` via `t(key, lang, ...)`, with the
corresponding key defined for both `uz` and `ru`, producing text equivalent in meaning to
today's output for both languages.

**Validates: Requirements 2.1**

Property 2: Bug Condition — Render self-ping keep-alive

_For any_ runtime where `RENDER_EXTERNAL_URL` is set, the fixed `Uzumchi/main.py` SHALL run a
background task that periodically issues a GET to `{RENDER_EXTERNAL_URL}/ping`; and _for any_
runtime where `RENDER_EXTERNAL_URL` is absent, the task SHALL log and return without raising
(safe no-op).

**Validates: Requirements 2.2**

Property 3: Bug Condition — Finance detail in Orders and daily report

_For any_ Orders view or daily report where finance order data exposes
`commission`/`sellerProfit`/`logistics`, the fixed handlers SHALL display per-order
commission and seller profit in addition to revenue.

**Validates: Requirements 2.3**

Property 4: Bug Condition — Finance aggregates and margin in weekly/monthly reports

_For any_ weekly or monthly report where finance order data is available, the fixed handlers
SHALL display aggregate commission, logistics, net (seller) profit, and the profit-margin
(rentabellik) percentage alongside revenue and order counts, with margin computed as
`seller_profit_total / revenue_total * 100` (and shown as `0%`/`—` when revenue is 0).

**Validates: Requirements 2.4, 2.5**

Property 5: Bug Condition — Delivered date formatting without NameError

_For any_ delivered-order notification that displays the buyer-received date, the fixed code
SHALL format the timestamp with a helper that is defined and imported in Uzumchi
(`utils/helpers.format_date`), so the delivered-check job completes without raising
`NameError` (and renders `—`/empty for a missing/zero timestamp).

**Validates: Requirements 2.6**

Property 6: Bug Condition — Data-layer reconciliation

_For any_ integration of finance reporting, the fixed data layer SHALL add finance parsing as
**new** functions while keeping `get_products` (raw list), `get_finance_orders` (Uzumchi
signature), `parse_invoices`→`StorageItem`, `summarize_orders`, and `get_storage_alerts`
returning their current shapes, so the AI advisor, competitor monitor, multi-shop, and
SKU-variant features keep functioning.

**Validates: Requirements 2.7**

Property 7: Preservation — Advanced features and existing contracts unchanged

_For any_ input where the bug condition does NOT hold, the fixed code SHALL produce the same
result as the original code, preserving the Gemini advisor, competitor monitor (incl.
`product_urls`/`competitor_tracking`), multi-shop (`set_active_shop`/`shop_ids`/
`active_shop_id`), SKU-variant display (`format_product_skus`/`_get_sku_variant_name`),
charts (`weekly_sales_chart`/`monthly_sales_chart`/`stock_pie_chart`),
`parse_invoices`/`get_storage_alerts`, `/ping` and `/health`, the
`get_sales_stats_from_products` fallback, and helpers `stock_icon`/`safe_float`/`safe_int`/
`short_name`.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8**

## Fix Implementation

### Fix-and-Preservation Analysis (summary)

| Defect (C sub-condition) | Fix surface (Uzumchi only) | Strategy | Preservation guard |
|---|---|---|---|
| 1.1 i18n drift | `locales/i18n.py`, `services/scheduler.py`, `handlers/analytics.py`, `handlers/main_menu.py` | Add new keys; replace inline blocks with `t()` | `t()` signature + existing keys untouched; new keys only |
| 1.2 keep-alive | `Uzumchi/main.py` | Add `self_ping()` coro + `create_task` | `/ping` + `/health` handlers unchanged; no-op when env absent |
| 1.3/1.4/1.5 finance reports | `services/uzum_api.py` (new fns), `handlers/main_menu.py`, `handlers/analytics.py` | Add `parse_finance_order`/`extract_finance_orders`/`summarize_finance_orders`; wire into reports | `summarize_orders` unchanged; finance is additive overlay |
| 1.6 ms_to_date | `services/scheduler.py`, `utils/helpers.py` | Use existing `format_date`; correct import | `format_date` already exists; no new global name needed |
| 1.7 data divergence | `services/uzum_api.py` | New finance fns only; keep `get_products` raw list + `get_finance_orders` signature | No `parse_product`/`extract_products` adoption |

### Change 1 — Centralize i18n (`locales/i18n.py` + 3 call sites)

**File:** `Uzumchi/locales/i18n.py`

Add new `TEXTS` keys (uz + ru) for every scheduler/report string. Do **not** modify the `t()`
function or any existing key. Proposed new keys (names indicative; final wording mirrors the
current inline copy):

- Scheduler — morning report: `sched_morning_title`, `sched_morning_body`
  (params: `total`, `delivered`, `cancelled`, `revenue`), `sched_morning_storage`
  (params: `paid`, `alert`, `warn`, `ok`).
- Scheduler — storage alerts: `sched_storage_header`, `sched_storage_line`
  (params: `icon`, `invoice_number`, `days`, `qty`).
- Scheduler — delivered: `sched_delivered` (param: `count`); optional detailed variant
  `sched_delivered_detail` (params: `name`, `sku`, `price`, `commission`, `profit`, `date`).
- Scheduler — rating: `sched_rating` (params: `shop_name`, `rating`).
- Scheduler — forecast: `sched_forecast_header`, `sched_forecast_line`
  (params: `icon`, `name`, `days`).
- Scheduler — returns: `sched_returns` (param: `count`).
- Reports — weekly: `report_weekly_body` (params: `total`, `delivered`, `cancelled`,
  `revenue`), `report_weekly_daily_header`, plus finance keys below.
- Reports — monthly: `report_monthly_body`, `report_monthly_weeks_header`, plus finance keys.
- Orders/daily finance keys (shared): `finance_commission`, `finance_logistics`,
  `finance_net_profit`, `finance_margin` (params as needed: `commission`, `logistics`,
  `profit`, `margin`).

Each key MUST have both `uz` and `ru` entries. Where existing keys already cover a string
(e.g. `report_today`, `report_weekly`, `report_monthly`, `orders_summary`,
`low_stock_header`, `out_of_stock_header`, `loading`, `no_data`), reuse them rather than
adding duplicates.

**File:** `Uzumchi/services/scheduler.py`
- Add `from locales.i18n import t`.
- In `run_morning_reports`, `run_storage_alerts`, `run_delivered_check`, `run_rating_check`,
  `run_forecast_check`, `run_returns_check`: replace each inline `if lang == "uz": ... else:`
  message construction with `t(key, lang, **params)`. Keep the control flow, dedup keys
  (`was_notified_today`), and `bot.send_message(..., parse_mode="HTML")` calls unchanged.

**File:** `Uzumchi/handlers/analytics.py`
- In `cmd_weekly` and `cmd_monthly`: replace the inline uz/ru report bodies with `t()` calls
  using the new `report_weekly_*` / `report_monthly_*` keys. The per-day / per-week bar-chart
  loop logic stays; only the surrounding header/label strings move to `t()`.

**File:** `Uzumchi/handlers/main_menu.py`
- In `cmd_orders` and `cmd_report_today`: route the report bodies through `t()`. Keep the
  existing `orders_summary`, `low_stock_header`, `out_of_stock_header` usage. Keep the
  `get_sales_stats_from_products` fallback branch intact (its text may also be moved to new
  keys but its behavior is unchanged).

### Change 2 — Self-ping keep-alive (`Uzumchi/main.py`)

- Add `import aiohttp` (module currently imports only `from aiohttp import web`).
- Read `RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "")`.
- Add an `async def self_ping()` coroutine modeled on the reference behavior: if `RENDER_URL`
  is empty, log "self-ping disabled (local mode)" and return; otherwise loop with
  `await asyncio.sleep(interval)` then GET `{RENDER_URL}/ping` inside a `try/except` that logs
  failures and continues.
- In `main()`, after the web server starts, schedule it: `asyncio.create_task(self_ping())`.
- Do **not** change `ping_handler` (`"pong"`) or `health_handler` (`"OK"`), nor the route
  registration for `/ping` and `/health`.

### Change 3 — Finance parsing + aggregation (`services/uzum_api.py`, additive)

Add three **new** functions; touch nothing existing:

- `extract_finance_orders(data: dict) -> list[dict]` — mirror of the reference extractor:
  pull from `orderItems` / `orders` / `items` / `content`, tolerate a bare list.
- `parse_finance_order(raw: dict) -> dict` — port the reference parser, returning
  `{id, order_id, status, date, date_issued, sell_price, commission, seller_profit,
  logistics, amount, sku_title, product_title}` (reading `sellPrice`/`sellerPrice`,
  `commission`, `sellerProfit`, `logisticDeliveryFee`, `dateIssued`, `skuTitle`,
  `productTitle`), all numeric fields defaulting to 0.
- `summarize_finance_orders(finance_raw: dict) -> dict` — **new aggregator** returning
  `{count, revenue, commission, logistics, net_profit, margin_pct}` where
  `revenue = Σ sell_price`, `commission = Σ commission`, `logistics = Σ logistics`,
  `net_profit = Σ seller_profit`, and
  `margin_pct = net_profit / revenue * 100 if revenue > 0 else 0`. This is intentionally
  separate from `summarize_orders` so the existing summary contract is untouched.

**Data-layer reconciliation rules (explicit, for 1.7 / Property 6):**
- `get_products(api_key, shop_id)` continues to return a **raw `list[dict]`**. Do NOT add or
  call `extract_products`/`parse_product` in any consumer path.
- `get_finance_orders(api_key, date_from=None, date_to=None, limit=100, offset=0)` keeps its
  **current signature** and continues to return the raw dict. The new `extract_finance_orders`
  / `parse_finance_order` / `summarize_finance_orders` consume that dict — the reference
  `get_finance_orders(api_key, shop_id, ...)` positional-`shop_id` signature is NOT adopted.
- `parse_invoices`→`StorageItem`, `get_storage_alerts`, and `summarize_orders` are unchanged
  and remain the source of truth for storage and order-count/revenue summaries.

### Change 4 — Wire finance detail into reports

- **Orders** (`handlers/main_menu.py::cmd_orders`): after the existing `summarize_orders`
  block, call `get_finance_orders(...)` → `summarize_finance_orders(...)` and, when
  `revenue > 0`, append commission and seller-profit lines via the `finance_*` `t()` keys.
  The 403 → `get_sales_stats_from_products` fallback branch is preserved and short-circuits
  before the finance block (no finance call when there are no orders).
- **Daily report** (`handlers/main_menu.py::cmd_report_today`): same overlay — append
  per-order commission / seller profit when finance data is present.
- **Weekly** (`handlers/analytics.py::cmd_weekly`): compute finance aggregates over the 7-day
  window and append commission, logistics, net profit, and margin % lines.
- **Monthly** (`handlers/analytics.py::cmd_monthly`): compute aggregates from per-order
  finance fields (not only `get_expenses`); display commission, logistics, net profit, and
  margin %. Keep the existing weekly-breakdown bar loop and the `get_expenses` line as a
  secondary/fallback figure so behavior degrades gracefully when finance data is empty.

All finance overlays are **conditional** (`if finance available / revenue > 0`) so that when
the finance endpoint returns nothing the reports render exactly as they do today.

### Change 5 — Delivered-date helper (`services/scheduler.py` + `utils/helpers.py`)

- When porting the delivered-order "buyer received on {date}" line into Uzumchi's
  `run_delivered_check`, format the timestamp with the **existing** `format_date(ts_ms)` from
  `utils/helpers.py` (returns `DD.MM.YYYY`), imported explicitly:
  `from utils.helpers import format_date`.
- Do **not** introduce a `ms_to_date` name. `format_date` already exists and is correct; the
  reference's `ms_to_date`/`ms_to_date_str` split (and its NameError) is not carried over.
- Optional hardening: if `date_issued` may be `0`/`None`, guard before calling (or rely on
  `format_date` returning a sensible value); the design choice is to skip/format-as-empty,
  never to raise.

## Testing Strategy

### Validation Approach

Two phases: first surface counterexamples that demonstrate each defect on the **unfixed**
Uzumchi code, then verify the fix produces the expected behavior and that non-buggy inputs
(the advanced features and existing contracts) are byte-for-byte preserved. Because this is a
text-bot with network side effects, tests target pure/parsing/aggregation functions and use
fakes for the bot, the API client, and the HTTP session.

### Exploratory Bug Condition Checking

**Goal:** Surface counterexamples that demonstrate each sub-defect BEFORE implementing the
fix; confirm or refute the root-cause analysis.

**Test Plan:** Write focused tests/assertions against the unfixed tree to observe the failure
modes; if a hypothesis is refuted, re-hypothesize before coding.

**Test Cases:**
1. **i18n drift (1.1):** Assert that `t()` does NOT yet contain keys for the morning/weekly/
   monthly/orders bodies, and that the scheduler/report sources contain inline
   `if lang == "uz"` blocks (will "fail" = confirm drift on unfixed code).
2. **Keep-alive (1.2):** Assert `Uzumchi/main.py` registers no background ping task and does
   not read `RENDER_EXTERNAL_URL` (confirms the gap).
3. **Finance reporting (1.3/1.4/1.5):** Feed a representative `/v1/finance/orders` payload and
   assert the current Orders/weekly/monthly text contains no commission/logistics/net-profit/
   margin tokens (confirms omission).
4. **ms_to_date (1.6 — edge case):** Port the reference delivered line verbatim into a scratch
   harness and assert it raises `NameError: ms_to_date` (confirms the latent defect we must
   avoid).
5. **Contract divergence (1.7):** Assert `get_products` returns a `list` (not a dict) and that
   `get_finance_orders` is keyword-`date_from` (not positional `shop_id`), establishing the
   contracts the merge must not break.

**Expected Counterexamples:** missing `t()` keys + inline blocks; no ping task; reports
without finance tokens; `NameError` on the verbatim port; list-vs-dict / signature mismatch.

### Fix Checking

**Goal:** For all inputs where the bug condition holds, the fixed function produces the
expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := fixed(input)
  ASSERT expectedBehavior(result)   // string via t(); ping task present;
                                     // finance tokens present; no NameError;
                                     // contracts preserved
END FOR
```

### Preservation Checking

**Goal:** For all inputs where the bug condition does NOT hold, the fixed function produces
the same result as the original.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT original(input) == fixed(input)
END FOR
```

**Testing Approach:** Property-based testing is recommended for preservation because it
generates many inputs across the domain and catches edge cases manual tests miss. Capture
the unfixed behavior of `get_products`, `summarize_orders`, `parse_invoices`,
`get_storage_alerts`, `format_product_skus`, and the AI/competitor prompt builders first,
then assert equality after the fix.

**Test Cases:**
1. **AI advisor preservation:** For random `stats`/`products`, assert
   `build_sales_analysis_prompt` and `build_storage_advice_prompt` outputs are unchanged.
2. **Competitor preservation:** For random saved-URL/product sets, assert `check_saved_urls`
   and `format_single_product_report` outputs are unchanged; DB table usage unchanged.
3. **Contract preservation:** Assert `get_products` still returns a list, `summarize_orders`
   still returns the same 6-key dict, `parse_invoices` still returns `StorageItem`s, and
   `get_finance_orders` keeps its signature.
4. **Endpoint preservation:** `/ping` returns `pong` and `/health` returns `OK` after the fix.
5. **Fallback preservation:** With orders-API 403, `cmd_orders` still uses
   `get_sales_stats_from_products`.

### Unit Tests

- `t()` returns defined uz + ru strings for every new key; `.format(**params)` succeeds for
  each parameterized key; unknown key still falls back to `[key]`.
- `parse_finance_order` maps all fields with 0-defaults for missing numerics.
- `extract_finance_orders` handles `orderItems` / `orders` / `items` / `content` / bare list.
- `summarize_finance_orders` computes revenue/commission/logistics/net_profit and
  `margin_pct`, including the `revenue == 0 → 0%` branch.
- `format_date(0)` / missing timestamp renders safely (no exception) in the delivered path.
- `self_ping()` returns immediately (no loop, no raise) when `RENDER_EXTERNAL_URL` is unset.

### Property-Based Tests

- **Margin invariant:** for any list of finance orders, `0 <= margin_pct <= 100` when all
  `seller_profit ∈ [0, sell_price]` and `revenue > 0`; `margin_pct == 0` when `revenue == 0`.
- **Aggregation = sum:** `summarize_finance_orders.revenue == Σ sell_price` (and likewise for
  commission/logistics/net_profit) across randomly generated finance payloads.
- **Preservation equivalence:** for randomly generated products/stats/invoices, the outputs of
  `summarize_orders`, `parse_invoices`, `format_product_skus`, and the prompt builders are
  identical before vs. after the fix (golden/serialized comparison).
- **i18n totality:** for every new key and `lang ∈ {uz, ru}`, `t(key, lang, **params)` returns
  a non-empty string that is not the `[key]` fallback.

### Integration Tests

- Full report flow with a fake bot + fake API: Orders, daily, weekly, monthly each render the
  finance overlay when finance data is present and render the legacy layout when it is empty.
- Delivered-check job runs end-to-end over a finance payload with `dateIssued` set and
  completes without `NameError`, emitting the received-date line via `format_date`.
- Startup wiring: with `RENDER_EXTERNAL_URL` set, `main()` schedules the `self_ping` task and
  `/ping` stays reachable; with it unset, startup proceeds and `self_ping` no-ops.
- Language switch: a user on `uz` and a user on `ru` receive equivalent scheduler/report
  messages sourced entirely from `t()`.
