# Competitor Shop / Revenue Fixes — Bugfix Design

## Overview

This design covers two independent, low-risk defects in the **Uzumchi** project. The
`uzum_seller_bot` project is a read-only reference and MUST NOT be touched.

- **FIX 1 — Robust competitor shop/seller name** (`services/competitor_monitor.py`).
  The competitor shop name renders as `🏪 —` because the name is extracted from a single
  narrow path in the API payload (`shop.name` / `shop.shopName` / `seller.name` /
  `seller.shopName`), and the HTML-fallback path hardcodes `"—"` without trying to parse
  the seller name from the already-fetched product-page HTML. The fix adds two small,
  pure helpers — `_extract_shop_name(payload)` (multi-field, priority-ordered, nested-safe)
  and `get_shop_from_html(html)` (parses embedded JSON / JSON-LD) — and wires them into
  `get_product_info_by_url` and `_get_product_from_api`. No public signatures change, and
  no extra network fetch is added (the existing `_fetch_product_html` result is reused).

- **FIX 2 — Net-of-returns revenue** (`services/uzum_api.py::get_sales_stats_from_products`).
  `total_revenue` is the sum of `quantitySold * price` per SKU, which overcounts versus the
  seller's real finance figure because returned units are not subtracted. The fix changes the
  accumulation to `total_revenue += max(0, sold - returned) * price`. `total_sold` and
  `total_returned` keep their current meaning (raw sums), all dict keys are unchanged, and the
  figure remains explicitly approximate ("taxminiy"/"приблизительный" labels in handlers stay).

Both fixes are surgical: they preserve every currently-working behavior and keep all public
function signatures and return shapes intact.

## Glossary

- **Bug_Condition (C)**: The condition that triggers a bug.
  - **C_shop**: a shop/seller name is resolvable from the API payload or product-page HTML, yet
    the current code yields `"—"`.
  - **C_revenue**: at least one SKU has `quantityReturned > 0`, so gross revenue overcounts.
- **Property (P)**: The desired behavior when the bug condition holds (shop name resolved; revenue
  netted of returns).
- **Preservation**: Behavior that MUST remain unchanged — genuinely-missing shop names stay `"—"`;
  prices / proxy / manual fallback are untouched; `total_sold` / `total_returned` and all dict keys
  stay identical; zero-return revenue is identical to today.
- **`_extract_shop_name(payload)`**: NEW pure helper in `competitor_monitor.py`. Given an API
  payload dict, returns the first non-empty shop/seller name across many candidate fields, else `""`.
- **`get_shop_from_html(html)`**: NEW pure helper in `competitor_monitor.py`. Parses the seller/shop
  name from product-page HTML (embedded JSON keys and/or JSON-LD), else `None`.
- **`get_product_info_by_url(uzum_url)`**: existing orchestrator that fetches HTML once and the API,
  then assembles the `info` dict (including `info["shop"]`).
- **`_get_product_from_api(product_id)`**: existing API-only extractor used by the orchestrator.
- **`get_sales_stats_from_products(api_key, shop_id)`**: existing product-based sales estimator.
- **F / F'**: original (unfixed) / fixed function.

## Bug Details

### Bug Condition — FIX 1 (shop name)

The bug manifests whenever a competitor's seller name is present in the data the bot already has
(API payload under a non-standard field, or the product-page HTML), but the current extraction is
too narrow — it checks only `shop.name`/`shop.shopName`/`seller.name`/`seller.shopName` in
`_get_product_from_api`, and the HTML-fallback branch in `get_product_info_by_url` hardcodes
`"shop": "—"`. As a result `info["shop"]` becomes `"—"` and the views render `🏪 —`.

**Formal Specification:**
```
FUNCTION isBugCondition_shop(X)
  INPUT: X = competitor context (api_payload: dict | None, html: str | None)
  OUTPUT: boolean

  RETURN (shopNameResolvable(X.api_payload) OR shopNameResolvable(X.html))
         AND currentExtractedShop(X) = "—"
END FUNCTION
```
where `shopNameResolvable(payload)` is true when `_extract_shop_name(payload)` would return a
non-empty string, and `shopNameResolvable(html)` is true when `get_shop_from_html(html)` would
return a non-empty string.

### Bug Condition — FIX 2 (revenue)

The bug manifests whenever the SKU list contains at least one returned unit, because gross revenue
(`sold * price`) is accumulated without subtracting returns.

**Formal Specification:**
```
FUNCTION isBugCondition_revenue(X)
  INPUT: X = list of products, each with a skuList of {quantitySold, quantityReturned, price}
  OUTPUT: boolean

  RETURN EXISTS sku IN flatten(X.skuList) WHERE int(sku.quantityReturned) > 0
END FUNCTION
```

### Examples

**FIX 1**
- API payload `{"seller": {"title": "ACME Store"}}` → today `"—"`; expected `"ACME Store"`.
- API payload `{"shopTitle": "BestShop"}` → today `"—"`; expected `"BestShop"`.
- API payload `{"shopInfo": {"title": "MegaShop"}}` → today `"—"`; expected `"MegaShop"`.
- API payload `{"sellerName": "TopSeller"}` → today `"—"`; expected `"TopSeller"`.
- API failed, HTML contains `"seller":{"title":"HtmlShop"}` → today `"—"`; expected `"HtmlShop"`.
- API failed, HTML JSON-LD `"brand":{"name":"BrandX"}` → today `"—"`; expected `"BrandX"`.
- Edge: payload `{"shop": {}}` and HTML with no seller markers → stays `"—"` (correct).

**FIX 2**
- One SKU `sold=100, returned=10, price=21,000` → gross `2,100,000`; net `90*21,000 = 1,890,000`.
- Observed real-world: estimate **2,131,470** (gross) vs seller cabinet figure **1,370,284**;
  netting returns moves the estimate toward the real figure while staying approximate.
- Edge: `sold=5, returned=8, price=1,000` → `max(0, 5-8)=0` contribution (never negative).
- Zero returns: `sold=50, returned=0, price=2,000` → net `100,000` = gross (unchanged).

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Competitor **prices** (API and HTML), the **manual price fallback**, and **proxy support**
  continue to work exactly as before; only shop-name resolution changes (Req 3.1).
- A competitor product with **no resolvable shop name** still displays `"—"` (Req 3.2).
- `get_sales_stats_from_products` returns the **same `total_sold` and `total_returned`** as today;
  only `total_revenue` changes (Req 3.3).
- Public functions `get_sales_stats_from_products`, `get_product_info_by_url`,
  `format_single_product_report`, and `check_saved_urls` keep their **signatures and return
  shapes** (Req 3.4).
- Orders fallback, storage free-days, AI features, menu, multi-shop, charts, scheduler, and the
  `/ping` / `/health` endpoints are **unaffected** (Req 3.5).

**Scope:**
All inputs where `isBugCondition_shop` is false (genuinely-missing seller name) and all SKU lists
where `isBugCondition_revenue` is false (no returns) must be completely unaffected by these fixes.
The revenue figure remains explicitly **approximate**; no cabinet finance call is added.

> The expected *correct* behavior for buggy inputs is defined in **Correctness Properties** below.

## Hypothesized Root Cause

**FIX 1 (shop name):**
1. **Narrow API extraction** — `_get_product_from_api` reads only `payload.shop`/`payload.seller`
   and then only `.name`/`.shopName`. Uzum payloads also expose the name under `seller.title`,
   `shopTitle`, `shopInfo.title`, `sellerName`, top-level `sellerTitle`/`companyName`, etc., so the
   first non-empty match is frequently missed.
2. **HTML path hardcodes `"—"`** — when the API fails entirely, `get_product_info_by_url` builds
   the fallback dict with `"shop": "—"` and never inspects the already-fetched HTML, even though
   the seller name is embedded in JSON / JSON-LD on the page.
3. **No reuse of fetched HTML** — the HTML is already retrieved once via `_fetch_product_html`;
   the name simply was never parsed from it.

**FIX 2 (revenue):**
1. **Returns ignored** — `total_revenue += sold * price` treats every sold unit as net revenue;
   refunded units inflate the estimate, diverging from the cabinet "tushum" figure.

## Correctness Properties

Property 1: Bug Condition — Robust Shop-Name Resolution

_For any_ competitor context where the bug condition holds (`isBugCondition_shop` returns true — a
shop/seller name is resolvable from the API payload or the product-page HTML), the fixed
`get_product_info_by_url` SHALL set `info["shop"]` to that resolved non-empty name (via
`_extract_shop_name` on the API payload, falling back to `get_shop_from_html` on the HTML when the
API name is empty/`"—"` or the HTML-fallback path is taken), and SHALL NOT render `"—"`.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation — Genuinely-Missing Names, Prices, Proxy, Manual Fallback

_For any_ competitor context where the bug condition does NOT hold (`isBugCondition_shop` returns
false — no resolvable name in either the API payload or HTML), the fixed code SHALL produce the same
result as the original (`info["shop"] == "—"`), and SHALL leave prices, the manual fallback, proxy
support, and all other `info` fields and public signatures unchanged.

**Validates: Requirements 2.4, 3.1, 3.2, 3.4**

Property 3: Bug Condition — Net-of-Returns Revenue

_For any_ product/SKU list where the bug condition holds (`isBugCondition_revenue` returns true — at
least one SKU has returns), the fixed `get_sales_stats_from_products` SHALL compute
`total_revenue == Σ over sku of max(0, sold - returned) * price`, such that no SKU contributes a
negative amount and `total_revenue <= grossRevenue` (the old estimate).

**Validates: Requirements 2.5**

Property 4: Preservation — Counts, Keys, Labels, and Zero-Return Revenue

_For any_ product/SKU list where the bug condition does NOT hold (`isBugCondition_revenue` returns
false — no returns), the fixed function SHALL produce a `total_revenue` identical to the original;
and for all inputs SHALL keep `total_sold` and `total_returned` as raw sums, keep all dict keys
(`total_sold`, `total_returned`, `total_revenue`, `low_stock_count`, `out_count`, `products_count`)
unchanged, and keep the user-facing figure labelled approximate without any cabinet finance call.

**Validates: Requirements 2.6, 2.7, 3.3, 3.4**

## Fix Implementation

### FIX 1 — `services/competitor_monitor.py`

**1a. NEW pure helper `_extract_shop_name(payload: dict) -> str`**

Checks candidate sources in priority order and returns the first non-empty, stripped string,
else `""`. Nested-dict lookups are guarded (treat non-dict nested values as absent).

Priority order (first non-empty wins):
1. `payload["seller"]["title"]`
2. `payload["seller"]["name"]`
3. `payload["seller"]["shopName"]`
4. `payload["seller"]["companyName"]`
5. `payload["shopTitle"]`
6. `payload["shopName"]`
7. `payload["shopInfo"]["title"]`
8. `payload["shopInfo"]["name"]`
9. `payload["sellerName"]`
10. `payload["shop"]["title"]`
11. `payload["shop"]["name"]`
12. `payload["shop"]["shopName"]`
13. top-level `payload["sellerTitle"]`
14. top-level `payload["companyName"]`

Implementation notes (design-level):
- Use a small internal accessor that, given the payload and a `("parent", "child")` or `("key",)`
  spec, safely returns a stripped string only when the resolved value is a non-empty `str`
  (or coercible scalar); otherwise `""`. Non-dict parents (e.g. `payload["seller"] == "ACME"`)
  should be handled — if a parent is itself a non-empty string, treat that string as the name for
  the bare-`shop`/`seller` cases (mirrors today's `str(shop)` behavior).
- Pure and synchronous: no I/O, no logging side effects required.

**1b. NEW pure helper `get_shop_from_html(html: str) -> str | None`**

Parses the seller/shop name from product-page HTML. Returns the first non-empty match, else `None`.
Mirrors the existing regex/JSON-LD style already used by `get_price_from_html` / `_title_from_html`.

Sources (in priority order):
1. Embedded JSON keys via regex: `"sellerTitle"`, `"shopTitle"`, `"sellerName"`
   (pattern `"<key>"\s*:\s*"([^"]+)"`).
2. A `"seller": { ... "title"/"name": "..." }` object — locate the `seller` object and read its
   `title` then `name`.
3. A `"shopInfo": { ... "title"/"name": "..." }` object — same approach.
4. JSON-LD `<script type="application/ld+json">`: parse blocks and read `brand.name` / `seller.name`
   (and a bare `brand`/`seller` string), reusing the JSON-LD scanning pattern already present in
   `get_price_from_html`.
- Returns `None` when no marker is found. Pure and synchronous (operates on the passed HTML string).

**1c. Wire into `get_product_info_by_url`**

- The HTML is already fetched once (`html = await _fetch_product_html(uzum_url)`); reuse it — do NOT
  add another fetch.
- When `api_data` is present: replace reliance on the narrow API shop with the robust resolver.
  Compute `api_shop = api_data.get("shop")`; if it is empty or `"—"`, try
  `shop_from_html = get_shop_from_html(html) if html else None` and use it when non-empty. Set
  `api_data["shop"]` to the resolved name, else `"—"`.
- In the **HTML-primary fallback** branch (API failed entirely): replace the hardcoded
  `"shop": "—"` with `get_shop_from_html(html)` when available, else `"—"`.

**1d. Update `_get_product_from_api`**

- Replace the narrow extraction:
  ```
  shop = payload.get("shop") or payload.get("seller") or {}
  shop_name = (shop.get("name") or shop.get("shopName") ...) or "—"
  ```
  with `shop_name = _extract_shop_name(payload) or "—"`. The returned dict shape is unchanged.

**1e. Views — no signature change**

- `check_saved_urls` already reads `shop = info.get("shop", "—")` and renders `🏪 {shop}`.
- `format_single_product_report` already renders `🏪 {shop}` only when `shop != "—"`.
- No changes required beyond verifying they now display the resolved name. (Confirmed via tests.)

### FIX 2 — `services/uzum_api.py::get_sales_stats_from_products`

**Single accumulation change** inside the per-SKU loop:
```
# before
total_revenue += sold * price
# after
net_sold = max(0, sold - returned)
total_revenue += net_sold * price
```
- `total_sold += sold` and `total_returned += returned` remain UNCHANGED (raw sums).
- All dict keys remain unchanged; only the `total_revenue` value differs when returns exist.
- The function docstring already says "taxminiy" (approximate); keep it. Handler labels
  ("taxminiy"/"приблизительный") are untouched, and no `/v1/finance/orders` call is added.

## Testing Strategy

### Validation Approach

Two-phase: first surface counterexamples that demonstrate each bug on UNFIXED code, then verify the
fix resolves the bug and preserves all other behavior. Tests live under `Uzumchi/tests/` and follow
the existing pytest conventions (see `tests/test_competitor_price.py`, `tests/test_finance.py`).

### Exploratory Bug Condition Checking

**Goal**: Demonstrate both bugs BEFORE implementing the fix; confirm or refute the root-cause
analysis. If refuted, re-hypothesize.

**Test Plan & Cases:**

*FIX 1 (shop name):*
1. **API non-standard field** — payload `{"seller": {"title": "ACME"}}` → assert resolved shop is
   `"ACME"`. On UNFIXED code the narrow extractor yields `"—"` → FAIL (confirms bug).
2. **HTML fallback** — API returns None, HTML contains `"seller":{"title":"HtmlShop"}` → assert
   resolved shop is `"HtmlShop"`. On UNFIXED code the branch hardcodes `"—"` → FAIL.
3. **JSON-LD brand** — HTML JSON-LD `"brand":{"name":"BrandX"}` → expected `"BrandX"`; UNFIXED → FAIL.

*FIX 2 (revenue):*
4. **With returns** — one SKU `sold=100, returned=10, price=21000` → expected
   `total_revenue == 1_890_000`. UNFIXED yields `2_100_000` → FAIL (confirms overcount).

**Expected Counterexamples:**
- Shop renders `🏪 —` despite a resolvable name in payload/HTML.
- `total_revenue` exceeds `Σ max(0, sold-returned)*price` whenever any SKU has returns.

### Fix Checking

**Goal**: For all inputs where the bug condition holds, the fixed function produces the expected
behavior.

**Pseudocode:**
```
FOR ALL X WHERE isBugCondition_shop(X) DO
  info := get_product_info_by_url'(X)
  ASSERT info.shop = resolvedShopName(X) AND info.shop != "—"
END FOR

FOR ALL X WHERE isBugCondition_revenue(X) DO
  result := get_sales_stats_from_products'(X)
  ASSERT result.total_revenue = SUM over sku OF max(0, sold - returned) * price
  ASSERT result.total_revenue <= grossRevenue(X)
END FOR
```

### Preservation Checking

**Goal**: For all inputs where the bug condition does NOT hold, the fixed function produces the same
result as the original.

**Pseudocode:**
```
FOR ALL X WHERE NOT isBugCondition_shop(X) DO
  ASSERT F(X).shop = F'(X).shop            // genuinely-missing stays "—"; prices/proxy/manual unchanged
END FOR

FOR ALL X WHERE NOT isBugCondition_revenue(X) DO
  ASSERT F(X).total_revenue = F'(X).total_revenue   // no returns => identical revenue
  ASSERT F(X).total_sold = F'(X).total_sold
  ASSERT F(X).total_returned = F'(X).total_returned
END FOR
```

**Testing Approach**: Property-based testing (Hypothesis is already present in the repo — see
`.hypothesis/`) is recommended for preservation, because it generates many inputs across the domain
and catches edge cases that fixed examples miss. Observe behavior on UNFIXED code first, then encode
those observations.

**Test Cases:**
1. **Missing shop preserved** — payload `{"shop": {}}`/no markers and HTML with no seller markers →
   verify `info["shop"] == "—"` before and after the fix.
2. **Prices/proxy/manual preserved** — verify min/max/price, `price_source`, `html_only`, and the
   manual-fallback path are byte-for-byte unchanged for representative inputs.
3. **Zero-return revenue preserved** — SKU lists with `returned == 0` produce identical
   `total_revenue` to the gross formula.
4. **Counts preserved** — `total_sold` / `total_returned` / `low_stock_count` / `out_count` /
   `products_count` unchanged for all inputs.

### Unit Tests

*Shop name (`_extract_shop_name`):*
- `seller.title`, `seller.name`, `seller.shopName`, `seller.companyName` shapes.
- `shopTitle`, `shopName` top-level keys.
- `shopInfo.title`, `shopInfo.name`.
- `sellerName`, `shop.title`/`shop.name`/`shop.shopName`.
- top-level `sellerTitle` / `companyName`.
- **priority order** — when several fields are present, the highest-priority one wins.
- nested non-dict / bare-string `shop`/`seller` handled safely.
- missing entirely → returns `""`.

*Shop name (`get_shop_from_html`):*
- HTML fixture with `"sellerTitle"` / `"shopTitle"` / `"sellerName"` JSON keys.
- HTML fixture with a `"seller":{"title":...}` object and a `"shopInfo":{...}` object.
- HTML fixture with JSON-LD `brand`/`seller` name.
- HTML with no seller markers → returns `None`.

*Orchestrator (`get_product_info_by_url`):*
- resolves shop from API payload (mock `_get_product_from_api`).
- resolves shop from HTML when API shop is empty/`"—"` (mock `_fetch_product_html`,
  `_get_product_from_api`).
- resolves shop from HTML on the API-failed fallback path.
- genuinely-missing → `info["shop"] == "—"`.
- no extra fetch: assert `_fetch_product_html` is called exactly once.

*Revenue (`get_sales_stats_from_products`):*
- with returns → `total_revenue == Σ max(0, sold-returned)*price` and `<=` gross.
- zero returns → identical to the old gross result.
- `returned > sold` SKU contributes `0` (never negative); aggregate `total_revenue >= 0`.
- `total_sold` / `total_returned` equal raw sums; all dict keys present and unchanged.

### Property-Based Tests

- **Shop name**: generate payloads placing a random non-empty name in a random candidate field →
  `_extract_shop_name` returns a non-empty string; generate payloads with all candidates empty →
  returns `""`.
- **Revenue net**: generate random SKU lists (random `sold`, `returned`, `price >= 0`) and assert
  `total_revenue == Σ max(0, sold-returned)*price`, `total_revenue >= 0`,
  `total_revenue <= Σ sold*price`, and `total_sold`/`total_returned` equal the raw sums.
- **Revenue preservation**: for SKU lists constrained to `returned == 0`, assert fixed
  `total_revenue` equals the gross formula.

### Integration Tests

- `check_saved_urls` renders the resolved shop name (not `🏪 —`) when a name is resolvable, for both
  `uz` and `ru`.
- `format_single_product_report` shows `🏪 {name}` when resolved and omits the line when `"—"`.
- Product-based sales report path surfaces the netted `total_revenue` while the handler still labels
  it approximate ("taxminiy"/"приблизительный").
