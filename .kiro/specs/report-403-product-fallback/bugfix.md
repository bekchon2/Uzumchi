# Bugfix Requirements Document

## Introduction

For sellers whose Uzum Seller API key only grants product **Read**/**Edit** scopes, every
order- and finance-related endpoint returns HTTP **403**. There is no separate "Orders/Finance"
permission available for this key type, so these endpoints will *always* fail for the affected
user — this is a permission limitation, not a transient error or a wrong key.

When such a user opens the report surfaces — the daily **"📊 Hisobot" / "📊 Отчёт"** report,
the weekly **"📈 Haftalik" / "📈 Недельный"** report, or the monthly **"📅 Oylik" / "📅 Месячный"**
report — the order/sales figures come back as all-zeros (because `get_fbs_orders` /
`get_fbs_orders_period` swallow the 403 and return `[]`). The result is a report that is empty
or silently zeroed-out, with no explanation, even though the bot *can* read product data and a
fallback function `get_sales_stats_from_products(api_key, shop_id)` already exists to compute
approximate sales statistics from product SKU fields.

This bugfix makes the report surfaces degrade gracefully: when orders/finance data is
unavailable due to the 403 permission limit, they fall back to product-based approximate stats
and show a clear, localized (uz + ru) note. When orders *are* available, behavior is unchanged.

### Observed Reproduction (real logs)

A user with a working API key opens the report section. The logs show:

```
GET /v2/fbs/orders        → 403
GET /v1/finance/orders     → 403
GET /v1/order/list         → 403
GET /v1/order              → 403
GET /v2/order              → 403
GET /v1/product/shop/116973 → 200   (products work)
[ORDERS] /v2/fbs/orders: 403 ruxsat yo'q
[ORDERS] Hamma endpoint 403 — ruxsat kerak!
```

The product endpoint succeeds (200) while all five order/finance endpoints return 403. The
report then renders with zeroed order totals and no fallback / no explanation.

### Bug Condition

```pascal
FUNCTION isBugCondition(X)
  INPUT: X — a report request {surface, api_key, shop_id}
         where surface IN {daily_report, weekly_report, monthly_report}
  OUTPUT: boolean

  // The key can read products but cannot read orders/finance (403 on all order endpoints)
  RETURN allOrderEndpointsReturn403(X.api_key)        // get_fbs_orders / get_finance_orders -> 403
         AND productEndpointSucceeds(X.api_key, X.shop_id)  // get_products -> 200
         AND X.surface IN {daily_report, weekly_report, monthly_report}
END FUNCTION
```

- **F** (original): report handlers call `get_fbs_orders` / `get_fbs_orders_period`, receive `[]`,
  summarize to zeros, and render an empty/zeroed report with no fallback and no note.
- **F'** (fixed): when `isBugCondition(X)` holds, report handlers fall back to
  `get_sales_stats_from_products` and render an approximate summary plus a localized note.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the daily report ("📊 Hisobot" / "📊 Отчёт") is opened and all order/finance endpoints return 403 THEN the system shows order/sales figures as all zeros (Jami: 0, Tushum: 0) with no fallback to product-based stats and no explanation of why.

1.2 WHEN the weekly report ("📈 Haftalik" / "📈 Недельный") is opened and all order/finance endpoints return 403 THEN the system renders an empty/zeroed report (0 orders per day, 0 revenue) with no product-based fallback and no explanation.

1.3 WHEN the monthly report ("📅 Oylik" / "📅 Месячный") is opened and all order/finance endpoints return 403 THEN the system renders an empty/zeroed report (0 orders per week, 0 revenue) with no product-based fallback and no explanation.

1.4 WHEN any report surface falls back due to 403 THEN the system shows no localized note telling the user that detailed order/finance data is unavailable for the current API key and that figures are approximate.

### Expected Behavior (Correct)

2.1 WHEN the daily report is opened and all order/finance endpoints return 403 THEN the system SHALL fall back to `get_sales_stats_from_products` and render a useful summary (total sold, total returned, estimated revenue, low-stock count, out-of-stock count, product count).

2.2 WHEN the weekly report is opened and all order/finance endpoints return 403 THEN the system SHALL fall back to `get_sales_stats_from_products` and render the product-based approximate summary instead of an empty/zeroed report.

2.3 WHEN the monthly report is opened and all order/finance endpoints return 403 THEN the system SHALL fall back to `get_sales_stats_from_products` and render the product-based approximate summary instead of an empty/zeroed report.

2.4 WHEN any report surface falls back due to 403 THEN the system SHALL display a clear, localized note in both uz and ru stating that detailed order/finance data is unavailable with the current API key (orders/finance permission not granted) and that the figures are approximate, computed from product data.

### Unchanged Behavior (Regression Prevention)

3.1 WHEN order/finance endpoints are available (orders permission present) THEN the daily, weekly, and monthly reports SHALL CONTINUE TO render the full order-based report including the existing conditional finance overlay (commission, logistics, net profit, margin).

3.2 WHEN orders are unavailable THEN the system SHALL CONTINUE TO honor the existing `get_sales_stats_from_products(api_key, shop_id)` contract and the product read path (`get_products`) without modifying their return shapes.

3.3 WHEN the "🛒 Buyurtmalar" / "🛒 Заказы" screen is used THEN it SHALL CONTINUE TO behave exactly as before, including its existing product-based fallback and 403 note.

3.4 WHEN the finance overlay, Gemini AI advisor, competitor monitor, multi-shop switching, SKU display/formatting, charts, and storage tracker are used THEN they SHALL CONTINUE TO work unchanged.

3.5 WHEN the `/ping` and `/health` endpoints are called THEN they SHALL CONTINUE TO respond exactly as before.

3.6 WHEN a report fails for a non-403 reason (network error, malformed data, rate limit) THEN the system SHALL CONTINUE TO surface the existing error handling rather than silently showing the product fallback as if it were authoritative.
