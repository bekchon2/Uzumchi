# Disable Legacy Scheduler Notifications — Bugfix Design

## Overview

The Telegram bot's `start_scheduler(bot)` function in `services/scheduler.py` registers
**nine** APScheduler jobs on the `AsyncIOScheduler` it builds. Only **two** of these were
ever requested by the user:

- `product_report_morning` — daily product digest, cron 09:00 `Asia/Tashkent`
  (runs `run_product_report`).
- `sale_check` — per-sale push detection, interval every 5 minutes
  (runs `run_sale_check`).

The other **seven** are legacy automatic notifications (`morning_reports`,
`storage_alerts`, `delivered_check`, `rating_check_morning`, `rating_check_evening`,
`forecast_check`, `returns_check`) that fire on their own schedules and send unsolicited,
often confusing messages.

**Fix approach (minimal, registration-only):** inside `start_scheduler`, remove the seven
`scheduler.add_job(...)` calls for the legacy jobs so they are never scheduled and never
fire. Keep the two `add_job` calls for `product_report_morning` and `sale_check` exactly as
they are today. Everything else about `start_scheduler` is unchanged: it still constructs
`AsyncIOScheduler(timezone=TASHKENT)` (where `TASHKENT = pytz.timezone("Asia/Tashkent")`),
and still returns that scheduler object to the caller (`main.py`, which then calls
`scheduler.start()`).

**Design decision — keep the legacy `run_*` async functions defined.** The seven legacy
coroutine functions (`run_morning_reports`, `run_storage_alerts`, `run_delivered_check`,
`run_rating_check`, `run_forecast_check`, `run_returns_check`) remain **defined** in the
module but are simply no longer referenced by any `add_job` call. They become dead but
harmless code. This is recommended over deleting them because:

- It minimizes churn — the diff is confined to deleting seven `add_job` blocks.
- It avoids breaking any import or test that might reference these symbols by name.
- A repository search (scoped to `/projects/sandbox/Uzumchi`) confirms **nothing imports
  the seven legacy `run_*` functions**, and nothing depends on them being *scheduled*. The
  only external consumers of the scheduler module are:
  - `main.py` → imports `start_scheduler`, calls it, then `scheduler.start()` (depends only
    on the returned scheduler object).
  - `tests/test_sale_detection.py` → imports `services.scheduler`, `detect_sales`,
    `build_current_map`, and calls `run_sale_check` — all preserved symbols.

  Therefore removing the legacy `run_*` *definitions* would be safe today, but keeping them
  is strictly lower-risk and equally correct from a behavior standpoint (an unreferenced
  coroutine never runs). Removal can be done later as independent cleanup if desired.

## Glossary

- **Bug_Condition (C)**: Holds for a job registration `X` whose job id is one of the seven
  legacy ids. These jobs must NOT be registered by the fixed scheduler.
- **Property (P)**: Desired behavior — the fixed scheduler contains **no** job with any of
  the seven legacy ids (`scheduler.get_job(id) is None`), so none of them ever fire.
- **Preservation**: The two requested jobs (`product_report_morning`, `sale_check`) remain
  registered with identical triggers/args, and the scheduler object's construction
  (timezone) and return value are unchanged. The behavior of `run_product_report` and
  `run_sale_check` (and their helpers `build_current_map`, `detect_sales`,
  `_sku_id_of`) is unchanged.
- **`start_scheduler(bot)`**: Factory in `services/scheduler.py` that builds an
  `AsyncIOScheduler(timezone=TASHKENT)`, registers jobs, and returns the scheduler. The
  caller starts it.
- **`TASHKENT`**: `pytz.timezone("Asia/Tashkent")`, the scheduler's timezone.
- **Legacy job id**: One of `morning_reports`, `storage_alerts`, `delivered_check`,
  `rating_check_morning`, `rating_check_evening`, `forecast_check`, `returns_check`.
- **F**: Original `start_scheduler` — registers all nine jobs.
- **F'**: Fixed `start_scheduler` — registers only `product_report_morning` and
  `sale_check`.

## Bug Details

### Bug Condition

The bug manifests because `start_scheduler` unconditionally calls `scheduler.add_job(...)`
for seven legacy notification jobs the user never requested. Each registered legacy job is
scheduled and will fire when its trigger time arrives, producing unsolicited messages. The
bug condition identifies each legacy job registration by its job id.

**Formal Specification:**
```
FUNCTION isBugCondition(X)
  INPUT: X — a job registration in start_scheduler, identified by its job id
  OUTPUT: boolean

  RETURN X.jobId IN {
           "morning_reports",       // 08:00 cron       -> run_morning_reports
           "storage_alerts",        // every 4 hours    -> run_storage_alerts
           "delivered_check",       // every 10 minutes -> run_delivered_check
           "rating_check_morning",  // 09:00 cron       -> run_rating_check
           "rating_check_evening",  // 18:00 cron       -> run_rating_check
           "forecast_check",        // 09:30 cron       -> run_forecast_check
           "returns_check"          // every 30 minutes -> run_returns_check
         }
END FUNCTION
```

Inputs where the bug condition does NOT hold and must be preserved:
```
// NOT bug condition — preserved exactly
X.jobId IN { "product_report_morning", "sale_check" }
```

### Examples

- **`morning_reports` (08:00 cron):** Expected — no job registered, no message sent.
  Actual (unfixed) — job registered; at 08:00 `Asia/Tashkent` sends "🌅 Ertalabki hisobot"
  with mostly-zero figures.
- **`forecast_check` (09:30 cron):** Expected — no job registered. Actual — at 09:30 sends
  "📉 Tovar tugash ogohlantirishlari" listing many "0 kun qoldi" items.
- **`storage_alerts` / `delivered_check` / `returns_check` (intervals):** Expected — no jobs
  registered. Actual — registered and fire every 4h / 10min / 30min respectively.
- **`rating_check_morning` & `rating_check_evening` (09:00 / 18:00 cron):** Expected — not
  registered. Actual — registered and fire, sending low-rating warnings.
- **Edge case — `product_report_morning` (09:00 cron):** This job and `rating_check_morning`
  share the same 09:00 trigger time but are distinct ids; only `product_report_morning` must
  remain. The fix must remove `rating_check_morning` while leaving `product_report_morning`
  intact.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- `start_scheduler` still creates `AsyncIOScheduler(timezone=TASHKENT)` and returns it; the
  caller (`main.py`) still calls `scheduler.start()` on the returned object.
- `product_report_morning` remains registered with `CronTrigger(hour=9, minute=0,
  timezone=TASHKENT)`, `args=[bot]`, `id="product_report_morning"`, `replace_existing=True`,
  bound to `run_product_report`.
- `sale_check` remains registered with `IntervalTrigger(minutes=5)`, `args=[bot]`,
  `id="sale_check"`, `replace_existing=True`, bound to `run_sale_check`.
- `run_product_report` and `run_sale_check` bodies (and helpers `build_current_map`,
  `detect_sales`, `_sku_id_of`, plus the `_seen_delivered` module state and the
  `PRODUCT_REPORT_MAX_ITEMS` / `LOW_STOCK_THRESHOLD` constants) are unchanged.
- Database helpers, handlers, multi-shop features, charts, `/ping`, `/health`, and `init_db`
  are unaffected.

**Scope:**
All inputs that do NOT involve registering one of the seven legacy job ids should be
completely unaffected by this fix. This includes:
- Registration and behavior of `product_report_morning` and `sale_check`.
- The scheduler object's construction (timezone) and its return to the caller.
- The continued *existence* of the legacy `run_*` function definitions (kept, unreferenced).

## Hypothesized Root Cause

This is not a logic defect but an **over-broad feature scope**: `start_scheduler` was
written to register a full suite of automatic notifications, but only two were actually
requested. The "root cause" is therefore the presence of seven unwanted
`scheduler.add_job(...)` registration calls.

1. **Excess registrations in `start_scheduler`**: Seven `add_job` calls schedule jobs the
   user never asked for. Removing those calls is the entire fix.
2. **No conditional/config gating**: The legacy jobs are added unconditionally with no flag
   to disable them, so they always fire. (The chosen fix removes the calls rather than
   adding configuration, per the requested minimal approach.)
3. **Coupling concern (ruled out)**: One might worry that removing registrations breaks
   importers. A scoped search confirms no module imports the seven legacy `run_*` functions
   and the only scheduler consumers depend on the returned object and the preserved
   `run_sale_check` / helper symbols — so removal of registrations is safe.

## Correctness Properties

Property 1: Bug Condition - Legacy Jobs Are Not Scheduled

_For any_ job id where the bug condition holds (`isBugCondition` returns true — i.e. one of
the seven legacy ids), the fixed `start_scheduler` SHALL NOT register that job: calling
`scheduler.get_job(id)` on the returned scheduler SHALL return `None`, so the job never
fires and its notification is never sent.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7**

Property 2: Preservation - Requested Jobs And Scheduler Construction Unchanged

_For any_ job id where the bug condition does NOT hold (`isBugCondition` returns false), the
fixed `start_scheduler` SHALL produce the same result as the original. Concretely, the
returned scheduler SHALL still contain `product_report_morning` (cron 09:00 `Asia/Tashkent`,
bound to `run_product_report`) and `sale_check` (interval 5 min, bound to `run_sale_check`)
with identical triggers and args; the scheduler SHALL still be an
`AsyncIOScheduler(timezone=Asia/Tashkent)` and SHALL still be returned to the caller; and
the behavior of `run_product_report` and `run_sale_check` SHALL be unchanged.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `services/scheduler.py`

**Function**: `start_scheduler(bot)`

**Specific Changes**:
1. **Remove the `morning_reports` registration**: delete the `scheduler.add_job(run_morning_reports, CronTrigger(hour=8, minute=0, ...), id="morning_reports", ...)` block.
2. **Remove the `storage_alerts` registration**: delete the `add_job(run_storage_alerts, IntervalTrigger(hours=4), id="storage_alerts", ...)` block.
3. **Remove the `delivered_check` registration**: delete the `add_job(run_delivered_check, IntervalTrigger(minutes=10), id="delivered_check", ...)` block.
4. **Remove both rating-check registrations**: delete the two `add_job(run_rating_check, ...)` blocks (`id="rating_check_morning"` at 09:00 and `id="rating_check_evening"` at 18:00).
5. **Remove the `forecast_check` registration**: delete the `add_job(run_forecast_check, CronTrigger(hour=9, minute=30, ...), id="forecast_check", ...)` block.
6. **Remove the `returns_check` registration**: delete the `add_job(run_returns_check, IntervalTrigger(minutes=30), id="returns_check", ...)` block.
7. **Keep unchanged**: the `AsyncIOScheduler(timezone=TASHKENT)` construction, the
   `product_report_morning` `add_job` block, the `sale_check` `add_job` block, and the final
   `return scheduler`.

**Explicitly NOT changed**:
- The seven legacy `run_*` async function definitions remain in the module (dead but
  harmless, no longer referenced).
- `run_product_report`, `run_sale_check`, and all helper functions / module state.
- Any other file (handlers, database, main.py, locales, utils).

After the fix, `start_scheduler` registers exactly two jobs and the legacy job ids resolve
to `None` via `scheduler.get_job(...)`.

## Testing Strategy

### Validation Approach

Two phases: first surface counterexamples on the UNFIXED code (legacy jobs present), then
verify the fix removes only the legacy registrations while leaving the two requested jobs
and the scheduler construction/return value intact. Tests call `start_scheduler` with a bot
double and inspect the returned scheduler's jobs via `scheduler.get_job(id)` — without
calling `scheduler.start()`, so no job actually executes.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix —
i.e. show that the legacy jobs ARE currently registered. Confirm the root cause (excess
`add_job` calls). If a legacy id is unexpectedly absent on unfixed code, re-hypothesize.

**Test Plan**: Construct a lightweight bot double (a plain object/stub; `start_scheduler`
only stores `bot` in `args` and never calls it during registration). Call
`scheduler = start_scheduler(fake_bot)` and assert each legacy id resolves to a registered
job. Run on UNFIXED code to observe these assertions; they encode the *desired post-fix*
state (`get_job(id) is None`), so on unfixed code they FAIL — confirming the bug.

**Test Cases**:
1. **Legacy ids present (unfixed) / absent (fixed)**: For each of the seven legacy ids,
   `scheduler.get_job(id)` — FAILS on unfixed code (job exists). (will fail on unfixed code)
2. **`morning_reports` at 08:00**: present on unfixed code. (will fail on unfixed code)
3. **`forecast_check` at 09:30**: present on unfixed code. (will fail on unfixed code)
4. **Interval jobs `storage_alerts` / `delivered_check` / `returns_check`**: present on
   unfixed code. (will fail on unfixed code)

**Expected Counterexamples**:
- `scheduler.get_job("morning_reports")` (and the other six ids) returns a non-`None` Job on
  unfixed code instead of `None`.
- Possible causes: the seven `scheduler.add_job(...)` calls in `start_scheduler` register
  these jobs unconditionally.

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed scheduler does
not register the job.

**Pseudocode:**
```
scheduler := start_scheduler(fake_bot)   // F'
FOR ALL id WHERE isBugCondition(id) DO
  ASSERT scheduler.get_job(id) IS None
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed
scheduler produces the same result as the original.

**Pseudocode:**
```
scheduler := start_scheduler(fake_bot)   // F'
FOR id IN { "product_report_morning", "sale_check" } DO
  ASSERT scheduler.get_job(id) IS NOT None
END FOR
// product_report_morning: CronTrigger hour=9 minute=0 timezone=Asia/Tashkent, func=run_product_report, args=[bot]
// sale_check:             IntervalTrigger minutes=5,                          func=run_sale_check,     args=[bot]
ASSERT scheduler.timezone == Asia/Tashkent
ASSERT start_scheduler returns the scheduler object
// behavioral preservation of the two job functions:
ASSERT run_product_report unchanged AND run_sale_check unchanged
```

**Testing Approach**: Property-based testing is recommended for the function-level
preservation of `run_sale_check` (its baseline/detect-sales behavior across many SKU maps),
because it generates many inputs and catches edge cases. Job-registration preservation is
naturally expressed as concrete assertions on the two known ids.

**Test Plan**: Observe behavior on UNFIXED code first — the two requested jobs are present
with their triggers, the scheduler timezone is `Asia/Tashkent`, and `run_product_report` /
`run_sale_check` behave a certain way — then write tests asserting those same observations
hold after the fix.

**Test Cases**:
1. **Requested jobs preserved**: `get_job("product_report_morning")` and
   `get_job("sale_check")` are non-`None` on unfixed code; assert still non-`None` after fix.
2. **Trigger details preserved**: `product_report_morning` is a cron at 09:00
   `Asia/Tashkent`; `sale_check` is a 5-minute interval — assert unchanged after fix.
3. **Scheduler construction/return preserved**: returned object is an `AsyncIOScheduler`
   with `Asia/Tashkent` timezone — assert unchanged after fix.
4. **`run_sale_check` / `run_product_report` behavior preserved**: existing sale-detection
   tests (e.g. `tests/test_sale_detection.py`: first-run baseline yields no push; strict
   decrease yields one push; increase yields none) continue to pass after fix.

### Unit Tests

- `start_scheduler(fake_bot)` returns an `AsyncIOScheduler` with `Asia/Tashkent` timezone.
- For each of the seven legacy ids, `scheduler.get_job(id) is None` after the fix.
- `scheduler.get_job("product_report_morning")` and `scheduler.get_job("sale_check")` are
  not `None` after the fix, with the expected trigger types.
- Total registered job count on the returned scheduler is exactly 2.

### Property-Based Tests

- Preservation of `run_sale_check` detection logic: generate random previous/current SKU
  quantity maps and assert the fixed module's `detect_sales` / `run_sale_check` behavior
  matches observed baseline behavior (no push on first pass; push only on strict decrease).
- Preservation of `build_current_map` over randomly generated active-product/SKU structures.

### Integration Tests

- Call `start_scheduler(fake_bot)`, then assert that enumerating
  `scheduler.get_jobs()` yields exactly the two requested job ids and none of the seven
  legacy ids.
- Smoke path mirroring `main.py`: build the scheduler and confirm the returned object is
  the one that would be passed to `scheduler.start()`, with only the two jobs registered
  (without actually starting it, so no notifications are dispatched in tests).
