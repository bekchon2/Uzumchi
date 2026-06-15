# Bugfix Requirements Document

## Introduction

The Uzumchi Telegram bot (the target/base codebase that this fix lands in) is the more
advanced of two divergent Uzum Market seller bots. It adds multi-shop support, a Gemini
AI advisor, competitor price monitoring, and SKU-variant display. However, relative to the
reference bot (`uzum_seller_bot`), Uzumchi is currently **broken/incomplete**: several
behaviors that sellers depend on either misbehave or are missing entirely.

This document treats those gaps as **bug conditions** to fix on the Uzumchi base, while
guaranteeing that Uzumchi's unique, more-advanced features keep working. The triggering
inputs (the "bug condition", `C(X)`) are the code paths and runtime situations described
below; the desired behavior after the fix is the corrected bot (`F'`).

The defects to address are:

- **Inconsistent translation handling** — user-facing text in the scheduler and report
  handlers is hardcoded inline per language instead of flowing through the central i18n
  catalog, producing duplicated and drifting translations.
- **Missing Render keep-alive** — there is no self-ping loop, so the service is allowed to
  sleep on Render's free tier and scheduled jobs / polling stop.
- **Missing detailed commission/profit reporting** — orders and the daily/weekly/monthly
  reports omit per-order commission, seller profit, logistics, and profit-margin (%).
- **A latent `ms_to_date` defect from the reference bot** that must NOT be carried over
  when porting the delivered-order notification behavior.
- **Data-layer divergence** that must be reconciled so the AI advisor, competitor monitor,
  multi-shop, and SKU-variant features continue to function after the merge.

## Bug Analysis

### Current Behavior (Defect)

The Uzumchi bot today exhibits the following incorrect or missing behavior:

1.1 WHEN the scheduler jobs and report handlers render user-facing text (morning reports, storage alerts, delivered notifications, orders, storage, today/weekly/monthly reports) THEN the system builds messages from hardcoded inline `if lang == "uz" / else` blocks instead of the central `locales/i18n.py` `t()` catalog, so translation strings are duplicated across files and drift out of sync.

1.2 WHEN the bot runs on Render's free tier and receives no inbound HTTP traffic for the platform idle window THEN the system has no self-ping keep-alive task, so the web service is allowed to spin down (sleep) and scheduled jobs plus polling stop until an external request wakes it.

1.3 WHEN a user opens Orders or the daily report THEN the system shows only order counts and gross revenue (via `summarize_orders`) and omits per-order commission, seller profit, and logistics cost, so net profit is never shown.

1.4 WHEN a user opens the weekly report THEN the system shows order counts and revenue only, with no commission, no logistics, no net profit, and no profit-margin (rentabellik) percentage.

1.5 WHEN a user opens the monthly report THEN the system derives only a coarse total-expenses figure from `get_expenses` and omits per-order commission, seller profit, and logistics breakdown, so the reported profitability is incomplete.

1.6 WHEN the delivered-order notification needs to display the buyer-received date (the behavior being copied from the reference bot) THEN the reference implementation calls `ms_to_date(...)` while only `ms_to_date_str` is imported in `services/scheduler.py`, raising a `NameError` at runtime; carried over as-is, this would crash the delivered-check job.

1.7 WHEN finance/profit reporting is added by importing the reference bot's data-layer functions THEN the reference contracts (`get_products` returning a raw dict consumed via `extract_products`/`parse_product`, `get_finance_orders(api_key, shop_id, ...)`, `get_storage_days_map`) differ from Uzumchi's contracts (`get_products` returning a raw list, `get_finance_orders(api_key, date_from, ...)`, `parse_invoices`→`StorageItem`/`get_storage_alerts`), so a naive merge would change data shapes the AI advisor, competitor monitor, multi-shop, and SKU-variant features rely on and break them.

### Expected Behavior (Correct)

After the fix, the bot SHALL behave as follows for the same triggering conditions:

2.1 WHEN the scheduler jobs and report handlers render user-facing text THEN the system SHALL obtain every user-facing string from the central i18n catalog (`locales/i18n.py`) via `t()`, with all required keys defined there for both `uz` and `ru`, so translations are consistent and maintained in one place.

2.2 WHEN the bot runs on Render's free tier with `RENDER_EXTERNAL_URL` set THEN the system SHALL run a background self-ping keep-alive task that periodically requests its own `/ping` endpoint to prevent the service from sleeping, and SHALL safely no-op (log and skip) when `RENDER_EXTERNAL_URL` is absent (local mode).

2.3 WHEN a user opens Orders or the daily report and finance order data exposes commission/sellerProfit/logistics THEN the system SHALL display per-order commission and seller profit where applicable in addition to revenue.

2.4 WHEN a user opens the weekly report THEN the system SHALL display aggregate commission, logistics, net (seller) profit, and the profit-margin (rentabellik) percentage alongside revenue and order counts.

2.5 WHEN a user opens the monthly report THEN the system SHALL display aggregate commission, logistics, net (seller) profit, and the profit-margin (rentabellik) percentage, computed from per-order finance fields rather than only a coarse total-expenses figure.

2.6 WHEN the delivered-order notification displays the buyer-received date THEN the system SHALL format it using a date-formatting helper that is correctly defined and imported (no `NameError`), so the delivered-check job runs to completion without crashing.

2.7 WHEN finance/profit reporting is integrated THEN the system SHALL reconcile the data layer so the new finance behavior coexists with the existing contracts — the AI advisor, competitor monitor, multi-shop, and SKU-variant features SHALL keep receiving the data shapes they currently expect (or be updated in lockstep) and SHALL keep functioning.

### Unchanged Behavior (Regression Prevention)

For inputs that do NOT trigger the bug, existing Uzumchi behavior MUST be preserved exactly:

3.1 WHEN a user uses the Gemini AI advisor (sales analysis, storage advice, or a free-form question) THEN the system SHALL CONTINUE TO build prompts from the outputs of `get_products`, `summarize_orders`, and `parse_invoices` and return Gemini responses exactly as it does today.

3.2 WHEN a user adds or lists competitor product URLs THEN the system SHALL CONTINUE TO extract the Uzum product id, fetch the title/price, persist to the `product_urls` and `competitor_tracking` tables, and render the comparison report unchanged.

3.3 WHEN a user has multiple shops THEN the system SHALL CONTINUE TO support `shop_ids`, `active_shop_id`, `set_active_shop`, and shop switching during onboarding and from settings, unchanged.

3.4 WHEN products are displayed THEN the system SHALL CONTINUE TO show SKU-variant breakdowns via `format_product_skus` and `_get_sku_variant_name`, and `utils/helpers.py` SHALL CONTINUE TO provide `stock_icon`, `safe_float`, `safe_int`, and `short_name` (these already exist and MUST NOT be removed or renamed when helpers are extended for date formatting).

3.5 WHEN charts are generated THEN the system SHALL CONTINUE TO expose the existing `weekly_sales_chart`, `monthly_sales_chart`, and `stock_pie_chart` functions in `services/charts.py` unchanged.

3.6 WHEN storage days and alerts are computed THEN the system SHALL CONTINUE TO use `parse_invoices`→`StorageItem` and `get_storage_alerts` (Uzumchi's data layer) for the existing storage features, regardless of any finance-reporting additions.

3.7 WHEN the `/ping` and `/health` endpoints are requested THEN the system SHALL CONTINUE TO respond successfully as they do today.

3.8 WHEN orders cannot be retrieved from the API (permission denied) THEN the system SHALL CONTINUE TO fall back to `get_sales_stats_from_products` for an approximate sales summary, unchanged.
