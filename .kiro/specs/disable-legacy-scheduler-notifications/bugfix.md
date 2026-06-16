# Bugfix Requirements Document

## Introduction

The Telegram bot uses an APScheduler instance (configured in `services/scheduler.py`,
function `start_scheduler`) that registers nine scheduled jobs. Of these, the user only
ever requested **two**:

- `product_report_morning` — the daily 09:00 (Asia/Tashkent) product report.
- `sale_check` — the per-sale push notification (interval, every 5 minutes).

The remaining **seven** jobs are legacy automatic notifications that the user never asked
for. They fire on their own schedule and send messages that the user finds confusing or
useless:

- At **08:00**, `morning_reports` sends "🌅 Ertalabki hisobot" (a morning report) that is
  mostly zeros.
- At **09:30**, `forecast_check` sends "📉 Tovar tugash ogohlantirishlari" (out-of-stock
  forecast) that shows "0 kun qoldi" for many items — buggy and confusing.
- `storage_alerts` (every 4 hours), `delivered_check` (every 10 minutes),
  `rating_check_morning` (09:00), `rating_check_evening` (18:00), and `returns_check`
  (every 30 minutes) all generate additional unsolicited noise.

These seven jobs are registered unconditionally inside `start_scheduler`, so they are
always scheduled and will always fire when their trigger time arrives. The fix (to be
specified in design/implementation, not here) will stop **registering** these legacy jobs
in `start_scheduler` so they are never scheduled and never send messages. The two
requested jobs must continue to work exactly as they do today.

## Bug Analysis

### Bug Condition C(X)

Let `X` be a scheduled-job registration in `start_scheduler`. The bug condition holds for
every legacy notification job that is registered (and will therefore fire):

```pascal
FUNCTION isBugCondition(X)
  INPUT: X — a job registered by start_scheduler (identified by its job id)
  OUTPUT: boolean

  RETURN X.jobId IN {
           "morning_reports",      // 08:00 cron      -> run_morning_reports
           "storage_alerts",       // every 4 hours   -> run_storage_alerts
           "delivered_check",      // every 10 minutes-> run_delivered_check
           "rating_check_morning", // 09:00 cron      -> run_rating_check
           "rating_check_evening", // 18:00 cron      -> run_rating_check
           "forecast_check",       // 09:30 cron      -> run_forecast_check
           "returns_check"         // every 30 minutes-> run_returns_check
         }
END FUNCTION
```

Inputs where the bug condition does NOT hold (the two requested jobs and everything else
in the application) must be preserved unchanged:

```pascal
// NOT bug condition — must be preserved
X.jobId IN { "product_report_morning", "sale_check" }
```

### Reproduction

1. Start the bot with the current `start_scheduler` (e.g. via `run.py` / `main.py`).
   All nine jobs are added to the `AsyncIOScheduler`.
2. Wait for (or trigger) the legacy schedules:
   - At **08:00 Asia/Tashkent**, the bot sends a message beginning with
     "🌅 Ertalabki hisobot" whose figures are mostly zeros.
   - At **09:30 Asia/Tashkent**, the bot sends a message beginning with
     "📉 Tovar tugash ogohlantirishlari" listing many items with "0 kun qoldi".
   - Across the day, additional messages arrive from `storage_alerts` (every 4h),
     `delivered_check` (every 10 min), `rating_check_morning` (09:00),
     `rating_check_evening` (18:00), and `returns_check` (every 30 min).
3. Observed result: the user receives unsolicited, confusing notifications that they never
   requested, in addition to the two reports they did request.

### Current Behavior (Defect)

1.1 WHEN `start_scheduler` runs THEN the system registers job `morning_reports` and at
08:00 Asia/Tashkent sends the "🌅 Ertalabki hisobot" message (mostly zeros) that the user
did not request.

1.2 WHEN `start_scheduler` runs THEN the system registers job `forecast_check` and at
09:30 Asia/Tashkent sends the "📉 Tovar tugash ogohlantirishilari" message showing
"0 kun qoldi" for many items, which is confusing and unrequested.

1.3 WHEN `start_scheduler` runs THEN the system registers job `storage_alerts` and sends
storage-alert messages every 4 hours, which the user did not request.

1.4 WHEN `start_scheduler` runs THEN the system registers job `delivered_check` and sends
delivered-order messages every 10 minutes, which the user did not request.

1.5 WHEN `start_scheduler` runs THEN the system registers jobs `rating_check_morning`
(09:00) and `rating_check_evening` (18:00) and sends rating-warning messages, which the
user did not request.

1.6 WHEN `start_scheduler` runs THEN the system registers job `returns_check` and sends
returns messages every 30 minutes, which the user did not request.

### Expected Behavior (Correct)

2.1 WHEN `start_scheduler` runs THEN the system SHALL NOT register job `morning_reports`,
and no "🌅 Ertalabki hisobot" message SHALL ever be sent automatically.

2.2 WHEN `start_scheduler` runs THEN the system SHALL NOT register job `forecast_check`,
and no "📉 Tovar tugash ogohlantirishilari" forecast message SHALL ever be sent
automatically.

2.3 WHEN `start_scheduler` runs THEN the system SHALL NOT register job `storage_alerts`,
and no automatic storage-alert message SHALL ever be sent.

2.4 WHEN `start_scheduler` runs THEN the system SHALL NOT register job `delivered_check`,
and no automatic delivered-order message SHALL ever be sent.

2.5 WHEN `start_scheduler` runs THEN the system SHALL NOT register jobs
`rating_check_morning` or `rating_check_evening`, and no automatic rating-warning message
SHALL ever be sent.

2.6 WHEN `start_scheduler` runs THEN the system SHALL NOT register job `returns_check`,
and no automatic returns message SHALL ever be sent.

2.7 WHEN `start_scheduler` runs THEN the scheduler SHALL register ONLY two jobs:
`product_report_morning` (cron 09:00 Asia/Tashkent) and `sale_check` (interval, every 5
minutes).

### Unchanged Behavior (Regression Prevention)

3.1 WHEN it is 09:00 Asia/Tashkent THEN the system SHALL CONTINUE TO run the
`product_report_morning` job (`run_product_report`) and send the daily product report
exactly as it does today (including the once-per-day `was_notified_today` guard).

3.2 WHEN the 5-minute `sale_check` interval elapses THEN the system SHALL CONTINUE TO run
the `sale_check` job (`run_sale_check`) and send per-sale push notifications exactly as it
does today (including baseline snapshot behavior on the first pass and strict
quantity-decrease detection thereafter).

3.3 WHEN a user interacts with on-demand handlers (products view, orders, storage,
competitor, AI) THEN the system SHALL CONTINUE TO respond exactly as before; these
handlers are independent of the scheduler registration.

3.4 WHEN multi-shop features, charts, `/ping`, and `/health` are used THEN the system
SHALL CONTINUE TO behave exactly as before.

3.5 WHEN the application initializes THEN `init_db` and the database helper functions
(`get_all_users`, `log_notification`, `was_notified_today`, `get_sku_snapshots`,
`save_sku_snapshots`, etc.) SHALL CONTINUE TO behave exactly as before.

3.6 WHEN the scheduler starts THEN the `AsyncIOScheduler` SHALL CONTINUE TO be created with
the `Asia/Tashkent` timezone and returned from `start_scheduler` as before; only the
registration of the seven legacy jobs is removed.

---

## Derived Bug Condition and Properties

**Key Definitions:**
- **F**: The original `start_scheduler` — registers all nine jobs.
- **F'**: The fixed `start_scheduler` — registers only `product_report_morning` and
  `sale_check`.

**Property: Fix Checking** — legacy jobs are not scheduled and never fire:

```pascal
// For every legacy job, the fixed scheduler must NOT contain it
FOR ALL X WHERE isBugCondition(X) DO
  scheduler ← F'(bot)
  ASSERT scheduler.get_job(X.jobId) IS NULL
END FOR
```

**Property: Preservation Checking** — requested jobs remain identical:

```pascal
// For the two requested jobs, F and F' register identical triggers/args
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT F(bot).get_job(X.jobId) = F'(bot).get_job(X.jobId)
END FOR
// Concretely: product_report_morning (cron 09:00 Asia/Tashkent) and
// sale_check (interval 5 min) remain registered with unchanged behavior.
```
