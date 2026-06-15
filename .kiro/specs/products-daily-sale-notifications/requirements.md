# Requirements Document

## Introduction

This feature extends the existing **Uzumchi** Telegram bot (aiogram 3, aiosqlite, APScheduler,
`pytz` `Asia/Tashkent`) with three additive seller capabilities derived from the approved design:

1. An **active-only single-page products view** that hides archived/inactive products and renders
   all remaining active products across one or more plain text messages with no pagination buttons.
2. A **daily 09:00 (Asia/Tashkent) product digest** pushed to each user at most once per day,
   summarizing total active products, total stock, low/out-of-stock counts, and the most urgent items.
3. A **near-real-time per-sale push** derived by polling the Uzum products endpoint every 5 minutes,
   snapshotting per-SKU active quantity, and notifying the user when a SKU's active quantity decreases.

All requirements are additive and non-destructive: every existing behaviour (orders, storage,
competitor monitoring, AI advisor, the 6-button main menu, multi-shop support, charts, existing
scheduler jobs, `/ping` & `/health`) MUST remain unchanged. New persistence and localization keys
MUST be purely additive, and `init_db` MUST remain migration-safe.

## Glossary

- **Uzumchi_Bot**: The existing aiogram 3 Telegram bot application being extended.
- **Products_View**: The `📦 Mahsulotlarim` screen rendered by `handlers/main_menu.py` (`_show_products_page`).
- **Active_Product**: A product for which `is_product_active(p)` returns `True` (no recognized inactive signal).
- **Inactive_Product**: A product carrying a recognized archived/inactive signal (status in the archived set, or `archived`/`isArchived` is `True`, or `active`/`isActive` is `False`).
- **Active_Filter**: The pure helper `is_product_active(p)` in `services/uzum_api.py`, the single source of truth for activeness.
- **Chunker**: The `build_chunks(header, blocks, limit)` function that packs a header and product blocks into messages.
- **TG_CHUNK_LIMIT**: The character bound (3500) used per message, safely under Telegram's 4096-char hard limit.
- **Daily_Report_Job**: The APScheduler cron job `run_product_report`, id `"product_report_morning"`, triggered at 09:00 Asia/Tashkent.
- **Sale_Check_Job**: The APScheduler interval job `run_sale_check`, id `"sale_check"`, triggered every 5 minutes.
- **SKU_Snapshot_Store**: The `sku_snapshots` table plus `get_sku_snapshots` / `save_sku_snapshots` helpers in `database.py`.
- **Current_Map**: The in-memory `dict[str, int]` mapping `sku_id` to `quantityActive` for active products in a sale check pass.
- **Sale_Event**: A detected strict decrease of a SKU's active quantity between two snapshots, reported as `(sku_id, sold, remaining)`.
- **Notification_Log**: The existing notification-tracking mechanism exposing `was_notified_today` and `log_notification`.
- **Low_Stock**: An active product whose total active quantity is `<= 5` and `> 0`.
- **Out_Of_Stock**: An active product whose total active quantity equals `0`.
- **I18n_Catalog**: The `TEXTS` structure in `locales/i18n.py` providing uz + ru localized strings.

## Requirements

### Requirement 1: Active-only products view

**User Story:** As a seller, I want the products view to show only my active (non-archived) products, so that my catalogue screen reflects what is actually live for sale.

#### Acceptance Criteria

1. WHEN a seller opens the Products_View, THE Uzumchi_Bot SHALL retrieve products via `get_products` and apply the Active_Filter to retain only Active_Products.
2. THE Active_Filter SHALL return `False` for any product whose `status` or `productStatus` (compared case-insensitively) is in the archived set `{ARCHIVED, ARCHIVE, INACTIVE, DELETED, HIDDEN, MODERATION_FAILED}`.
3. THE Active_Filter SHALL return `False` for any product where `archived` is `True`, `isArchived` is `True`, `active` is `False`, or `isActive` is `False`.
4. WHERE a product carries none of the recognized status or flag fields, THE Active_Filter SHALL return `True`.
5. WHEN the Products_View is rendered, THE Uzumchi_Bot SHALL exclude every Inactive_Product from the displayed listing.
6. IF the set of Active_Products is empty, THEN THE Uzumchi_Bot SHALL display the localized no-data message.

### Requirement 2: Single-page listing without pagination

**User Story:** As a seller, I want all my active products on one continuous listing, so that I can scroll through everything without clicking pagination buttons.

#### Acceptance Criteria

1. WHEN the Products_View renders a non-empty set of Active_Products, THE Uzumchi_Bot SHALL display all Active_Products across one or more messages using the Chunker.
2. THE Uzumchi_Bot SHALL NOT attach inline pagination markup (no `products_page_*` or `products_noop` callbacks) to any Products_View message.
3. WHEN the Chunker packs product blocks, THE Chunker SHALL preserve the ordered concatenation of all input blocks across the produced messages so that no block is dropped, duplicated, or reordered.
4. THE Chunker SHALL produce each message with length less than or equal to TG_CHUNK_LIMIT, except a message consisting of a single block that itself exceeds TG_CHUNK_LIMIT.
5. WHEN the Products_View includes a header, THE Uzumchi_Bot SHALL place the header in the first message only and include the active product count and total active quantity in that header.
6. WHEN multiple messages are produced, THE Uzumchi_Bot SHALL send the first message by editing the loading message and send each subsequent message as a new message without a keyboard.
7. IF a stale pagination callback (`products_page_*` or `products_noop`) is received from a previously sent message, THEN THE Uzumchi_Bot SHALL acknowledge the callback and re-render the single Products_View without raising an error.

### Requirement 3: Daily product digest scheduling

**User Story:** As a seller, I want a daily morning summary of my catalogue, so that I start each day knowing my stock health without opening the bot.

#### Acceptance Criteria

1. THE Daily_Report_Job SHALL be registered as an APScheduler cron job with id `"product_report_morning"` triggered at 09:00 in the `Asia/Tashkent` timezone.
2. WHEN the Daily_Report_Job triggers, THE Uzumchi_Bot SHALL iterate over all users returned by `get_all_users`.
3. IF `was_notified_today(user_id, "product_report")` reports that a user has already received the digest that day, THEN THE Uzumchi_Bot SHALL skip sending the digest to that user.
4. WHEN the Uzumchi_Bot sends the digest to a user, THE Uzumchi_Bot SHALL record the send via `log_notification(user_id, "product_report")`.
5. WHILE iterating over users, THE Uzumchi_Bot SHALL isolate each user's processing in error handling so that a failure for one user does not abort processing of remaining users.
6. WHILE iterating over users, THE Uzumchi_Bot SHALL pace successive sends with an asynchronous delay to respect Telegram rate limits.

### Requirement 4: Daily product digest content

**User Story:** As a seller, I want the daily digest to summarize my catalogue accurately, so that I can act on low and out-of-stock items.

#### Acceptance Criteria

1. WHEN the Uzumchi_Bot builds a user's digest, THE Uzumchi_Bot SHALL apply the Active_Filter and compute totals over Active_Products only.
2. THE digest total active count SHALL equal the number of Active_Products.
3. THE digest total stock SHALL equal the sum of `calc_total_qty` over all Active_Products.
4. THE digest SHALL report the Low_Stock count as the number of Active_Products with total active quantity `<= 5` and `> 0`, and the Out_Of_Stock count as the number of Active_Products with total active quantity equal to `0`.
5. THE digest SHALL include a list of the most urgent items, limited to a bounded number of low-stock and out-of-stock items.
6. THE Uzumchi_Bot SHALL render the digest using the user's language from I18n_Catalog in both uz and ru.

### Requirement 5: Per-sale notification scheduling and detection

**User Story:** As a seller, I want to be notified shortly after a unit sells, so that I can track sales in near real time even though the orders API is unavailable (returns 403).

#### Acceptance Criteria

1. THE Sale_Check_Job SHALL be registered as an APScheduler interval job with id `"sale_check"` triggered every 5 minutes.
2. WHEN the Sale_Check_Job triggers, THE Uzumchi_Bot SHALL, for each user, retrieve products via `get_products`, apply the Active_Filter, and build the Current_Map of `sku_id` to active quantity for Active_Products.
3. WHEN building the Current_Map, THE Uzumchi_Bot SHALL coerce each `sku_id` to a string using `skuId` when present and otherwise `id`.
4. IF a SKU provides neither `skuId` nor `id`, THEN THE Uzumchi_Bot SHALL skip that SKU and exclude it from the Current_Map.
5. WHEN comparing the Current_Map against the stored snapshot, THE Uzumchi_Bot SHALL produce a Sale_Event for a SKU if and only if that SKU is present in both the previous snapshot and the Current_Map and the previous quantity is strictly greater than the current quantity.
6. WHEN a Sale_Event is produced, THE Uzumchi_Bot SHALL report `sold` equal to the positive difference (previous minus current) and `remaining` equal to the current quantity.
7. IF a SKU is absent from the previous snapshot, or its quantity is unchanged or increased, THEN THE Uzumchi_Bot SHALL produce no Sale_Event for that SKU.
8. IF the stored snapshot for a user and shop is empty, THEN THE Uzumchi_Bot SHALL store the Current_Map as the baseline and send no push for that user during that pass.
9. WHEN a sale-check pass completes for a user and shop, THE Uzumchi_Bot SHALL save the Current_Map via `save_sku_snapshots`.
10. WHILE iterating over users, THE Uzumchi_Bot SHALL isolate each user's processing in error handling and pace sends with an asynchronous delay.

### Requirement 6: Per-sale notification content

**User Story:** As a seller, I want each sale notification to tell me what sold and how much is left, so that I can decide whether to restock.

#### Acceptance Criteria

1. WHEN the Uzumchi_Bot sends a Sale_Event push, THE Uzumchi_Bot SHALL include the product title, the variant name resolved via `_get_sku_variant_name`, the number sold, and the remaining stock.
2. THE Uzumchi_Bot SHALL render the sale push using the user's language from I18n_Catalog in both uz and ru.

### Requirement 7: SKU snapshot persistence

**User Story:** As a developer, I want SKU quantities persisted reliably between polls, so that sale detection is accurate and migration-safe.

#### Acceptance Criteria

1. THE Uzumchi_Bot SHALL create the `sku_snapshots` table within `init_db` using `CREATE TABLE IF NOT EXISTS` with a unique constraint on `(user_id, shop_id, sku_id)`.
2. THE SKU_Snapshot_Store SHALL store each `sku_id` as TEXT and each `qty` as a non-negative integer.
3. WHEN `save_sku_snapshots(user_id, shop_id, mapping)` is invoked, THE SKU_Snapshot_Store SHALL upsert each `(sku_id, qty)` pair so that the row for `(user_id, shop_id, sku_id)` exists with the given quantity and a refreshed `updated_at`.
4. WHEN `get_sku_snapshots(user_id, shop_id)` is invoked, THE SKU_Snapshot_Store SHALL return a `dict[str, int]` of all matching rows, and SHALL return an empty dict when no rows match.
5. WHEN a mapping is saved and then read back for the same `(user_id, shop_id)`, THE SKU_Snapshot_Store SHALL return a mapping equal to that mapping with keys coerced to string and values coerced to integer.
6. WHEN the same unchanged mapping is saved repeatedly, THE SKU_Snapshot_Store SHALL yield identical stored quantities (idempotent for unchanged values).

### Requirement 8: Localization additivity

**User Story:** As a seller using uz or ru, I want all new messages localized, so that the new features read naturally in my language without breaking existing translations.

#### Acceptance Criteria

1. THE I18n_Catalog SHALL add the keys `product_report_title`, `product_report_body`, `product_report_item`, `sale_push_title`, and `sale_push_item`, each resolving to a non-empty string in both uz and ru.
2. THE I18n_Catalog SHALL provide `product_report_body` with formattable parameters `total_active`, `total_stock`, `low_count`, and `out_count`, and `sale_push_item` with formattable parameters `product`, `variant`, `sold`, and `remaining`.
3. WHEN new localization keys are added, THE Uzumchi_Bot SHALL preserve all existing I18n_Catalog keys and their values unchanged.
4. WHEN a new key is formatted with its documented parameters, THE I18n_Catalog SHALL produce a string containing no unresolved `{` placeholders.

### Requirement 9: Preservation of existing features

**User Story:** As an existing user, I want all current bot capabilities to keep working exactly as before, so that the new features add value without regressions.

#### Acceptance Criteria

1. THE Uzumchi_Bot SHALL preserve the existing orders view behaviour unchanged.
2. THE Uzumchi_Bot SHALL preserve the existing storage view, including the free-days overlay, unchanged.
3. THE Uzumchi_Bot SHALL preserve the existing competitor monitoring features, including price tracking, shop name resolution, manual entry, and proxy handling, unchanged.
4. THE Uzumchi_Bot SHALL preserve the existing AI advisor (Gemini) features unchanged.
5. THE Uzumchi_Bot SHALL preserve the 6-button main menu keyboard unchanged.
6. THE Uzumchi_Bot SHALL preserve multi-shop selection behaviour unchanged.
7. THE Uzumchi_Bot SHALL preserve chart generation features unchanged.
8. THE Uzumchi_Bot SHALL preserve all existing scheduler jobs (`morning_reports`, `storage_alerts`, `delivered_check`, `rating_check_*`, `forecast_check`, `returns_check`) unchanged.
9. THE Uzumchi_Bot SHALL keep the `/ping` and `/health` endpoints operational.

### Requirement 10: Migration safety and non-destructive changes

**User Story:** As an operator, I want the upgrade to apply cleanly to existing databases, so that deployment does not lose or corrupt data.

#### Acceptance Criteria

1. WHEN `init_db` runs against an existing database, THE Uzumchi_Bot SHALL remain migration-safe and SHALL NOT alter or drop the existing `users`, `notification_log`, `competitor_tracking`, or `product_urls` tables or their helpers.
2. WHERE the `sku_snapshots` table already exists, THE Uzumchi_Bot SHALL leave existing snapshot rows intact when `init_db` runs.
3. THE Uzumchi_Bot SHALL introduce no new third-party dependencies, using only the already-present stack (`aiogram` 3, `aiosqlite`, `APScheduler`, `pytz`, and `Hypothesis` for tests).
