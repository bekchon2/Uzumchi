# Report 403 Product Fallback — Bugfix Design

## Overview

For API keys that only carry product **Read/Edit** scopes, every order/finance endpoint
returns HTTP **403**. `get_fbs_orders` / `get_fbs_orders_period` swallow that 403 and return
`[]`, so the three report surfaces — daily (`cmd_report_today`), weekly (`cmd_weekly`) and
monthly (`cmd_monthly`) — summarize to all-zeros and render an empty/zeroed report with no
explanation, even though the bot can still read products and an approximate sales calculator
(`get_sales_stats_from_products`) already exists.

The fix makes the three report surfaces **degrade gracefully**: when the order list comes back
empty *and* product-based stats are available, the handler renders an approximate, product-based
summary (total sold, total returned, estimated revenue, low-stock, out-of-stock, product count)
together with a clear localized (uz + ru) note that detailed order/finance data is unavailable
for the current API key and the figures are approximate. When orders are present, every report
renders exactly as today, including the conditional finance overlay.

The approach mirrors the fallback that `cmd_orders` (the "🛒 Buyurtmalar" screen) already
implements, factored into one small additive helper to avoid duplicating the rendering logic
across three handlers.

**Scope of change:** all edits are confined to `/projects/sandbox/Uzumchi`. `uzum_seller_bot`
is read-only reference and is not touched. No new subdirectories; only additive edits to existing
files plus one small new helper module under `handlers/`.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug — a report surface (daily / weekly /
  monthly) is requested, all order/finance endpoints return 403 (so `get_fbs_orders*` returns
  `[]`), while the product endpoint succeeds and product stats are computable.
- **Property (P)**: The desired behavior when C holds — the report falls back to
  `get_sales_stats_from_products` and renders the approximate product-based summary plus a
  localized "permission not granted / figures approximate" note, instead of an empty/zeroed report.
- **Preservation**: When orders are present, the existing full order-based report (including the
  conditional finance overlay) renders unchanged; the `get_sales_stats_from_products`,
  `get_products`, and `get_fbs_orders*` return contracts stay as-is; the Buyurtmalar screen,
  Gemini/competitor/multi-shop/SKU/charts/storage features, and `/ping`/`/health` endpoints are
  unaffected.
- **cmd_report_today**: Daily report handler in `handlers/main_menu.py` (triggered by
  "📊 Hisobot" / "📊 Отчёт").
- **cmd_weekly / cmd_monthly**: Weekly/monthly report handlers in `handlers/analytics.py`
  (triggered by "📈 Haftalik" / "📈 Недельный" and "📅 Oylik" / "📅 Месячный").
- **get_fbs_orders / get_fbs_orders_period**: Order fetchers in `services/uzum_api.py` that try
  five endpoints and return `[]` when all fail (including the all-403 case). **Return contract is
  unchanged by this fix.**
- **get_sales_stats_from_products**: Product-based approximate sales calculator returning
  `{total_sold, total_returned, total_revenue, low_stock_count, out_count, products_count}`, or
  `{}` on failure. **Contract unchanged.**
- **summarize_orders**: Reduces an order list to `{total, delivered, cancelled, processing,
  shipped, revenue}`. `total == 0` for an empty list.

## Bug Details

### Bug Condition

The bug manifests when a user with a product-only API key opens any of the three report surfaces.
All order/finance endpoints return 403, so `get_fbs_orders*` returns `[]`, `summarize_orders`
yields `total == 0` and `revenue == 0`, and the handler renders zeros with no fallback and no
explanation — despite product data being readable.

Because `get_fbs_orders` deliberately swallows the 403 and returns `[]` (a contract relied on
elsewhere — e.g. `cmd_orders` and the scheduler), the handler cannot directly see the 403. The
fix therefore detects the condition indirectly: **order list empty AND product stats available**.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input — report request {surface, api_key, shop_id}
         where surface IN {daily_report, weekly_report, monthly_report}
  OUTPUT: boolean

  orders        := get_fbs_orders*(input.api_key, ...)   // [] when all endpoints 403
  product_stats := get_sales_stats_from_products(input.api_key, input.shop_id)

  RETURN length(orders) == 0
         AND productStatsAvailable(product_stats)         // non-empty dict, products_count > 0
END FUNCTION
```

`productStatsAvailable(s)` is true when `s` is a non-empty dict with `products_count > 0`. This
guards against the non-403 product-failure case, where `get_sales_stats_from_products` returns
`{}` and the fallback must NOT engage.

### Key Design Decision — distinguishing "403 / no orders permission" from "genuinely zero orders"

Two options were considered:

- **(a) Emptiness + successful product fetch as the trigger** — treat `orders == []` AND product
  stats available as the fallback condition. Requires no change to `get_fbs_orders`.
- **(b) Signal the 403 explicitly** — have `get_fbs_orders` / `get_sales_*` return or raise a
  distinct "permission denied" marker so the handler can tell 403 apart from a real empty day.

**Chosen: (a).** Option (b) would change the `get_fbs_orders` return contract (currently `[]`),
which is relied upon by `cmd_orders`, the scheduler, and the AI sales analysis path — a wider blast
radius and a regression risk. Option (a) is the simplest robust approach and is already the exact
pattern `cmd_orders` uses today, keeping the three report surfaces consistent with an existing,
shipped behavior.

**Documented tradeoff:** On a *genuinely* zero-order day (orders legitimately empty, key has full
permissions), the report will also show the approximate product-based stats and the note. This is
acceptable because (1) the note is explicitly worded as "approximate / computed from product data",
so nothing is presented as authoritative; (2) showing product-derived sold/returned/stock figures
is strictly more useful than an all-zeros report; and (3) it keeps the trigger logic trivial and
robust without touching `get_fbs_orders`. A truly zero-sales *and* zero-product shop (no products)
fails `productStatsAvailable`, so it correctly falls through to the normal (empty) report rather
than the fallback.

### Examples

- **Daily, all-403 orders, 200 products** (the reported case): expected — header + approximate
  sold/returned/estimated-revenue block + product count + low-stock + out-of-stock + note; actual
  (unfixed) — "Jami: 0 | ✅ 0 | ❌ 0 | 💰 Tushum: 0 so'm" with no note.
- **Weekly, all-403 orders, 200 products**: expected — fallback summary + note; actual (unfixed) —
  zeroed totals plus a 7-day chart of all-`░`/0 bars.
- **Monthly, all-403 orders, 200 products**: expected — fallback summary + note; actual (unfixed) —
  zeroed totals plus a 4-week chart of all-0 bars.
- **Daily, orders present** (edge / preservation): full order-based report with finance overlay,
  no fallback, no note — unchanged.
- **Weekly, orders present but product fetch itself fails with a non-403 error**: `product_stats`
  is `{}`, `productStatsAvailable` is false, no fallback engages — existing behavior preserved.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- When orders are present, daily/weekly/monthly reports render the full order-based report,
  including the existing conditional finance overlay (commission, logistics, net profit, margin).
- `get_sales_stats_from_products(api_key, shop_id)`, `get_products`, and `get_fbs_orders*` keep
  their exact return shapes and semantics.
- The "🛒 Buyurtmalar" / "🛒 Заказы" screen (`cmd_orders`) keeps its existing product-based fallback
  and 403 note exactly as-is.
- Finance overlay, Gemini AI advisor, competitor monitor, multi-shop switching, SKU
  display/formatting, charts, storage tracker, and the `/ping` & `/health` endpoints are untouched.
- Non-403 failures continue to surface through the existing per-handler `except` blocks rather
  than masquerading as an authoritative report.

**Scope:**
All inputs where the order list is non-empty (orders permission present), and all inputs where
product stats are unavailable (`get_sales_stats_from_products` returns `{}` / no products), are
completely unaffected by this fix. The new branch is reachable only when `orders == []` AND
product stats are available.

> The expected *correct* behavior for the bug condition is defined formally in
> **Correctness Properties → Property 1**.

## Hypothesized Root Cause

1. **Missing fallback in report handlers**: `cmd_report_today`, `cmd_weekly`, and `cmd_monthly`
   summarize `get_fbs_orders*` output directly and never branch to the product-based calculator,
   even though `cmd_orders` already demonstrates the pattern. This is the primary cause.

2. **Silent 403 swallowing**: `get_fbs_orders` returns `[]` on all-403, so the handlers receive an
   empty list indistinguishable (without extra context) from a real zero-order day — and currently
   make no attempt to recover or explain.

3. **No localized note**: There is no i18n key telling the user that orders/finance permission is
   not granted and the figures are approximate, so even the existing `cmd_orders` fallback uses
   inline hard-coded strings rather than shared keys.

4. **Duplication risk**: Three handlers would each need the same fallback text, inviting copy-paste
   drift — motivating one shared additive builder.

## Correctness Properties

Property 1: Bug Condition - Product-based fallback on 403 orders

_For any_ report request to a daily, weekly, or monthly surface where the order list is empty
(all order/finance endpoints returned 403) AND product stats are available (isBugCondition returns
true), the fixed handler SHALL fall back to `get_sales_stats_from_products` and render an
approximate summary — total sold, total returned, estimated revenue, low-stock count,
out-of-stock count, and product count — together with a localized (uz + ru) note stating that
detailed order/finance data is unavailable for the current API key and the figures are
approximate, instead of an empty/zeroed report.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

Property 2: Preservation - Order-present and non-bug paths unchanged

_For any_ input where the bug condition does NOT hold (isBugCondition returns false) — orders are
present, or product stats are unavailable, or the surface is not a report — the fixed code SHALL
produce the same result as the original: the full order-based report with its conditional finance
overlay when orders are present; unchanged `get_sales_stats_from_products` / `get_products` /
`get_fbs_orders*` contracts; an unchanged Buyurtmalar screen; unchanged finance overlay, Gemini,
competitor, multi-shop, SKU, charts, and storage behavior; unchanged `/ping` & `/health`; and
non-403 failures still surfaced through existing error handling.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**

## Fix Implementation

### Changes Required

Assuming the root cause analysis is correct, the fix is additive across four files plus one small
new helper module. **No existing function signature or return contract changes.**

---

**File (new): `handlers/report_fallback.py`** — shared, minimal, additive

**Function**: `build_product_fallback_report(product_stats: dict, lang: str) -> str`

- Pure function: takes the dict from `get_sales_stats_from_products` and a language, returns the
  rendered HTML text block.
- Composes the summary from new i18n keys (`report_fallback_summary`) using the six fields
  (`total_sold`, `total_returned`, `total_revenue`, `products_count`, `low_stock_count`,
  `out_count`) and appends the localized note (`report_fallback_note`).
- Imports only `from locales.i18n import t`. No project-state, no I/O — trivially unit-testable.
- Also expose a tiny predicate `product_stats_available(stats: dict) -> bool` returning
  `bool(stats) and stats.get("products_count", 0) > 0`, used by all three handlers as the
  fallback guard (encodes `productStatsAvailable`).

> Alternative location considered: adding the builder to `utils/helpers.py`. Rejected to avoid
> introducing an i18n dependency into the otherwise pure formatting helpers; a dedicated module
> keeps the layering clean. Both handlers import from this one module.

---

**File: `handlers/main_menu.py` — `cmd_report_today`**

1. After computing `stats = summarize_orders(orders)` and fetching `products`, compute
   `total_qty`, `low_stock`, `out_of_stock` as today (unchanged).
2. Add a branch: when `stats["total"] == 0`, call
   `product_stats = await get_sales_stats_from_products(user["api_key"], user["shop_id"])`
   and, if `product_stats_available(product_stats)`, build the report as:
   the daily header + `build_product_fallback_report(product_stats, lang)` + the existing
   low-stock / out-of-stock name lists (these are already computed from `products`). **Skip** the
   zeroed orders block and **skip** the finance overlay in this branch (finance is also 403).
3. When `stats["total"] > 0` (orders present) OR product stats unavailable, render exactly the
   current full report including the conditional finance overlay — unchanged.
4. `get_products` stays inside the `try`, so a non-403 product failure still raises into the
   existing `except` block (preserves 3.6). Reuse the same pattern shape as `cmd_orders`.

---

**File: `handlers/analytics.py` — `cmd_weekly`**

1. After `orders = await get_fbs_orders_period(...)` and `stats = summarize_orders(orders)`, add a
   branch: when `stats["total"] == 0`, fetch `product_stats` and, if
   `product_stats_available(...)`, render the weekly header + `build_product_fallback_report(...)`
   and return — **instead of** the zeroed body, the all-zero daily chart, and the finance overlay.
2. When orders are present, render exactly as today (body + finance overlay + daily chart) —
   unchanged.

---

**File: `handlers/analytics.py` — `cmd_monthly`**

1. Same pattern: when `stats["total"] == 0`, fetch `product_stats` and, if available, render the
   monthly header + `build_product_fallback_report(...)` and return — **instead of** the zeroed
   body, weekly chart, expenses/profit block, and finance overlay.
2. When orders are present, render exactly as today — unchanged. (`get_expenses` is only reached on
   the orders-present path, so its behavior is preserved.)

---

**File: `locales/i18n.py`** — additive keys only; `t()` and all existing keys untouched

Add the following new entries to `TEXTS` (uz + ru):

- `report_fallback_summary` — multi-line body template with placeholders
  `{total_sold}`, `{total_returned}`, `{total_revenue}`, `{products_count}`,
  `{low_stock_count}`, `{out_count}`. Example (uz):
  ```
  📊 <b>Mahsulot asosidagi taxminiy hisobot</b>
  📦 Jami sotilgan: <b>{total_sold}</b> dona
  ↩️ Qaytarilgan: <b>{total_returned}</b> dona
  💰 Taxminiy tushum: <b>{total_revenue:,.0f} so'm</b>
  🗂 Tovar turlari: <b>{products_count}</b> ta
  ⚠️ Kam qolgan: <b>{low_stock_count}</b> | 🚫 Tugagan: <b>{out_count}</b>
  ```
  ru mirror with «Приблизительный отчёт по товарам», «Всего продано», «Возвращено»,
  «Ориентировочная выручка», «Видов товаров», «Мало», «Закончились».
- `report_fallback_note` — the permission note. Example (uz):
  ```
  ⚠️ <i>Buyurtma/moliya ma'lumotlari uchun API kalitga ruxsat berilmagan —
  ko'rsatilgan raqamlar tovar ma'lumotlaridan olingan taxminiy qiymatlar.</i>
  ```
  ru: «⚠️ <i>Доступ к данным заказов/финансов для API-ключа не предоставлен — показанные
  цифры приблизительные, рассчитаны из данных о товарах.</i>»

`build_product_fallback_report` concatenates `t("report_fallback_summary", lang, **product_stats)`
and `t("report_fallback_note", lang)`. (`product_stats` already contains every placeholder key,
so it can be splatted directly; `t()` ignores extras via its existing `format` guard.)

## Testing Strategy

### Validation Approach

Two phases: first surface counterexamples that demonstrate the bug on UNFIXED code (the report
shows zeros / no note when orders are 403 but products are readable); then verify the fix renders
the fallback for the bug condition and preserves the full report and all unrelated behavior.

Because handlers are async aiogram message handlers, the most decoupled and reliable unit under
test is the new pure builder `build_product_fallback_report` plus the i18n keys, complemented by an
integration test that simulates the all-403-orders + 200-products path through a handler with the
API functions mocked.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples demonstrating the bug BEFORE implementing the fix; confirm the
root cause (missing fallback branch). If refuted, re-hypothesize.

**Test Plan**: Drive a report handler (e.g. `cmd_report_today`) with `get_fbs_orders` mocked to
return `[]` (simulating all-403) and `get_products` / `get_sales_stats_from_products` mocked to
return realistic non-empty product data with `total_sold > 0`. Capture the text passed to
`msg.edit_text`. Run on UNFIXED code.

**Test Cases**:
1. **Daily 403 fallback** — press "📊 Hisobot": assert the rendered text contains the approximate
   sold/returned/revenue figures and the permission note (will FAIL on unfixed code — shows zeros,
   no note).
2. **Weekly 403 fallback** — "📈 Haftalik": assert fallback summary + note (will FAIL on unfixed).
3. **Monthly 403 fallback** — "📅 Oylik": assert fallback summary + note (will FAIL on unfixed).
4. **Edge — empty orders + no products** (`products_count == 0`): assert NO fallback note appears
   (guards against false trigger).

**Expected Counterexamples**:
- Rendered daily/weekly/monthly text contains "Jami: 0 / Всего: 0" and "0 so'm / 0 сум" with no
  fallback summary and no permission note.

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed handler produces the
fallback summary plus the localized note.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  text := render(reportHandler_fixed(input))
  ASSERT text CONTAINS approximateSummary(total_sold, total_returned, total_revenue,
                                          products_count, low_stock_count, out_count)
  ASSERT text CONTAINS permissionApproximateNote(input.lang)
  ASSERT text DOES NOT present zeroed order totals as authoritative
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed handler
produces the same result as the original.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT reportHandler_original(input) == reportHandler_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation because preservation
is a universal claim over the non-bug input domain (orders-present states and product-unavailable
states), and generated inputs catch edge cases manual tests miss.

**Test Plan**: Observe behavior on UNFIXED code for the orders-present path (full report + finance
overlay) and for the product-unavailable path (`product_stats == {}` ⇒ no fallback), then write
property-based tests asserting those observed outputs are unchanged after the fix.

**Test Cases**:
1. **Orders-present preservation** — observe the full order-based report (incl. finance overlay)
   for a non-empty order list on unfixed code; assert identical after fix; no note injected.
2. **Product-unavailable preservation** — with `orders == []` and `get_sales_stats_from_products`
   returning `{}`, observe the existing (zeroed) report on unfixed code; assert identical after fix
   (no fallback, no note).
3. **Contract preservation** — assert `get_sales_stats_from_products`, `get_products`,
   `get_fbs_orders` / `get_fbs_orders_period` return shapes are unchanged.
4. **Buyurtmalar preservation** — assert `cmd_orders` rendering is byte-identical before/after.

### Unit Tests

- `build_product_fallback_report(product_stats, lang)` for `lang in {"uz", "ru"}`: asserts every
  field (sold, returned, estimated revenue, product count, low-stock, out-of-stock) appears and the
  note is appended; revenue formatted with thousands separators.
- `product_stats_available(...)`: true for `{products_count: 5, ...}`; false for `{}` and for
  `{products_count: 0}`.
- i18n key presence: `report_fallback_summary` and `report_fallback_note` exist for both `uz` and
  `ru`; `t()` and all existing keys are unchanged (extend the existing `tests/test_i18n.py` style).

### Property-Based Tests

- Generate random non-negative product-stat dicts and assert `build_product_fallback_report` never
  raises and always includes the note and all six figures (Property 1 over the builder domain).
- Generate random non-empty order lists and assert the orders-present render path is byte-identical
  before/after the fix (Property 2 preservation).
- Generate the product-unavailable case and assert no fallback/note is emitted (Property 2).

### Integration Tests

- **All-403 orders + 200 products**: mock `get_fbs_orders` / `get_fbs_orders_period` → `[]`,
  `get_products` → realistic list, `get_sales_stats_from_products` → non-empty stats; drive each of
  `cmd_report_today`, `cmd_weekly`, `cmd_monthly` with a fake `Message`; assert the captured
  `edit_text` payload contains the fallback summary + note and no authoritative zeroed totals.
- **Orders present**: mock `get_fbs_orders*` → non-empty; assert full report + finance overlay and
  no note (integration-level preservation).
- **Non-403 product failure**: `get_sales_stats_from_products` → `{}`; assert no fallback/note and
  existing error/empty handling intact.
