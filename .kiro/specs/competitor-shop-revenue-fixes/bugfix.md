# Bugfix Requirements Document

## Introduction

This spec covers two defects observed on the running Uzumchi bot. Both are confined to the `Uzumchi` project (the `uzum_seller_bot` project is a read-only reference and MUST NOT be modified).

- **BUG 1 — Competitor shop/seller name shows "🏪 —".** In the competitor-monitoring views (`services/competitor_monitor.py`: `check_saved_urls` and `format_single_product_report`), the competitor's shop/seller name renders as a dash ("—") even though prices now display correctly. The shop name is extracted too narrowly from the API payload, and the HTML-fallback path hardcodes the shop to "—" without attempting to parse it from the product-page HTML.

- **BUG 2 — Product-based revenue estimate is too high.** In `services/uzum_api.py::get_sales_stats_from_products`, `total_revenue` is computed as the sum of `quantitySold * price` per SKU. This overcounts versus the seller's real finance figure ("tushum"). Because the real cabinet finance number is behind the seller-cabinet login and a finance API permission the user's key does not have (`/v1/finance/orders` returns 403 — a permission limit, not geo), it cannot be fetched automatically. The approved approach is to make the *estimate* more accurate by netting out returns, while keeping it clearly labelled as approximate.

Both fixes must preserve all currently working behavior and keep public function signatures intact.

## Bug Analysis

### Current Behavior (Defect)

**BUG 1 — Competitor shop name**

1.1 WHEN a competitor product is fetched and the Uzum API payload exposes the seller name under a field other than `shop.name`/`shop.shopName` or `seller.name`/`seller.shopName` (e.g. `seller.title`, `shopTitle`, `shopInfo.title`, `sellerName`) THEN `_get_product_from_api` fails to extract it and the system sets `shop` to "—".

1.2 WHEN the price/data comes from the HTML-fallback path (API failed entirely) THEN the system hardcodes `shop` to "—" and makes no attempt to parse the shop/seller name from the product-page HTML, even when the HTML contains it.

1.3 WHEN `check_saved_urls` renders a monitored item whose `shop` is "—" THEN the system displays the line `🏪 —`.

1.4 WHEN `format_single_product_report` renders a saved product whose `shop` is "—" THEN the system omits/shows the shop as a dash, so the seller name never appears even when it is actually available.

**BUG 2 — Revenue overcounting**

1.5 WHEN `get_sales_stats_from_products` aggregates SKU sales THEN the system computes `total_revenue += quantitySold * price` per SKU, ignoring returned units (`quantityReturned`).

1.6 WHEN a shop has returned units THEN the system reports a `total_revenue` materially higher than the seller's real finance figure (observed example: estimate **2,131,470** vs real **1,370,284**).

### Expected Behavior (Correct)

**BUG 1 — Competitor shop name**

2.1 WHEN a competitor product is fetched from the API THEN the system SHALL extract the shop/seller name robustly, checking multiple candidate fields (e.g. `seller.title`, `seller.name`, `seller.shopName`, `shopTitle`, `shopInfo.title`, `shopInfo.name`, `sellerName`, `shop.title`, `shop.name`, `shop.shopName`) and use the first non-empty value found.

2.2 WHEN only HTML is available (API price/data missing or API failed entirely) THEN the system SHALL attempt to parse the shop/seller name from the product-page HTML (e.g. embedded JSON keys such as `"sellerTitle"`, `"shopTitle"`, `"seller":{"title":...}`, or JSON-LD `brand`/`seller`).

2.3 WHEN a shop/seller name is successfully resolved (from API or HTML) THEN the competitor views (`check_saved_urls`, `format_single_product_report`) SHALL display that name instead of "—".

2.4 WHEN no shop/seller name can be found from either the API payload or the HTML THEN the system SHALL keep "—" as the displayed value.

**BUG 2 — Revenue estimate**

2.5 WHEN `get_sales_stats_from_products` aggregates SKU sales THEN the system SHALL compute revenue net of returns as `sum(max(0, quantitySold - quantityReturned) * price)` per SKU, so that no SKU contributes a negative amount.

2.6 WHEN `get_sales_stats_from_products` returns its result THEN the system SHALL keep the existing return dict keys unchanged (`total_sold`, `total_returned`, `total_revenue`, `low_stock_count`, `out_count`, `products_count`), with only the `total_revenue` calculation changed.

2.7 WHEN the revenue figure is presented to the user THEN the system SHALL continue to label it as an approximate estimate ("taxminiy"/"приблизительный") and SHALL NOT claim it is exact, nor attempt to fetch the cabinet finance number.

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the competitor API/HTML returns price data THEN the system SHALL CONTINUE TO display competitor prices, the manual fallback, and proxy support exactly as before (only shop-name resolution changes).

3.2 WHEN a competitor product genuinely has no resolvable shop name THEN the system SHALL CONTINUE TO display "—".

3.3 WHEN `get_sales_stats_from_products` reports counts THEN the system SHALL CONTINUE TO return the same `total_sold` and `total_returned` values as today (only the revenue calculation is adjusted).

3.4 WHEN any caller invokes the public functions `get_sales_stats_from_products`, `get_product_info_by_url`, `format_single_product_report`, or `check_saved_urls` THEN the system SHALL CONTINUE TO accept the same signatures and return the same shapes.

3.5 WHEN the user uses the orders fallback view, storage free-days, AI features, the menu, multi-shop support, charts, the scheduler, or the `/ping` and `/health` endpoints THEN the system SHALL CONTINUE TO behave exactly as before.

## Bug Condition Derivation

### Bug Condition Functions

```pascal
FUNCTION isBugCondition_shop(X)
  INPUT: X = competitor product context (API payload and/or product-page HTML)
  OUTPUT: boolean

  // A resolvable shop/seller name exists in the API payload or HTML,
  // but current extraction returns "—".
  RETURN shopNameResolvable(X.api_payload) OR shopNameResolvable(X.html)
         AND currentExtractedShop(X) = "—"
END FUNCTION
```

```pascal
FUNCTION isBugCondition_revenue(X)
  INPUT: X = shop SKU list
  OUTPUT: boolean

  // At least one SKU has returned units, so gross revenue overcounts.
  RETURN EXISTS sku IN X.skuList WHERE sku.quantityReturned > 0
END FUNCTION
```

### Properties (Fix Checking)

```pascal
// Property: Shop name resolution
FOR ALL X WHERE isBugCondition_shop(X) DO
  result := get_product_info_by_url'(X)
  ASSERT result.shop = resolvedShopName(X) AND result.shop != "—"
END FOR
```

```pascal
// Property: Net-of-returns revenue
FOR ALL X WHERE isBugCondition_revenue(X) DO
  result := get_sales_stats_from_products'(X)
  ASSERT result.total_revenue = SUM over sku OF max(0, sku.quantitySold - sku.quantityReturned) * sku.price
  ASSERT result.total_revenue <= grossRevenue(X)   // never higher than the old estimate
END FOR
```

### Preservation Goal

```pascal
// Property: Preservation
FOR ALL X WHERE NOT isBugCondition_shop(X) DO
  ASSERT F(X).shop = F'(X).shop          // genuinely-missing names stay "—"; price/proxy/manual unchanged
END FOR

FOR ALL X WHERE NOT isBugCondition_revenue(X) DO
  ASSERT F(X).total_revenue = F'(X).total_revenue   // no returns => identical revenue
  ASSERT F(X).total_sold = F'(X).total_sold
  ASSERT F(X).total_returned = F'(X).total_returned
END FOR
```

## Reproduction

**BUG 1**
1. Add/track a competitor Uzum product URL whose seller name is exposed only under a non-standard field (or which resolves via the HTML-fallback path).
2. Open the competitor monitoring view (or save a single product).
3. Observe the rendered line shows `🏪 —` even though prices display correctly.

**BUG 2**
1. For a shop that has returned units, open the product-based sales report.
2. Observe `total_revenue` ≈ **2,131,470** while the seller's real cabinet finance figure ("tushum") is **1,370,284** — the estimate is materially higher because returns are not netted out.

- **F** (original): `total_revenue += quantitySold * price`; shop extracted only via `shop.name`/`shop.shopName`/`seller.name`/`seller.shopName`, HTML path hardcodes "—".
- **F'** (fixed): robust multi-field + HTML shop-name resolution; `total_revenue = sum(max(0, quantitySold - quantityReturned) * price)`, labelled approximate.
