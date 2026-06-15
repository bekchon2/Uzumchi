# Storage / Menu / Competitor-Price / AI Fixes — Bugfix Design

## Overview

This design specifies concrete, file-by-file fixes for four reported defects in the
`/projects/sandbox/Uzumchi` Telegram bot. Scope is **strictly the `Uzumchi` repository**;
`uzum_seller_bot` is read-only reference and MUST NOT be touched.

The four bugs and the targeted strategy for each:

1. **Storage free-days countdown missing** — `cmd_storage` only renders stock levels. Fix:
   fetch invoices (`get_invoices`), parse with `parse_invoices` into `StorageItem`s, compute
   `free_days_left = max(0, FREE_DAYS - days_stored)` (reusing the existing `FREE_DAYS = 60`
   constant), and render a free-storage section alongside the existing stock view. When invoices
   are empty/403, keep the stock view and add a localized "data unavailable" note. Add new uz+ru
   i18n keys; do not change `t()` or existing keys.

2. **Daily Report still present** — remove the `📊 Hisobot`/`📊 Отчёт` button from
   `main_menu_keyboard` (6 buttons remain) and delete the `cmd_report_today` handler plus its
   now-dead wiring in `handlers/main_menu.py`. Keep `report_fallback.py` (pure, separately tested)
   but drop its now-unused import from `main_menu.py`. Update keyboard + report-integration tests.

3. **Competitor price not shown for a pasted URL** — add `UZUM_PROXY` env support (read at call
   time, passed as aiohttp `proxy=`) in `competitor_monitor`, and add a manual-price fallback FSM
   flow in `competitor_url_received` so the user always sees a comparison. Add localized note +
   manual-entry prompt strings.

4. **AI Совет broken despite a valid Groq key** — move provider env reads from module-import-time
   constants to call-time `os.getenv` reads inside `_all_providers()`, so keys loaded by
   `load_dotenv()` (which `main.py` runs *after* importing the handlers that import `gemini_ai`)
   are honored at runtime. Optionally add an early `load_dotenv()` in `gemini_ai.py` as
   defense-in-depth.

The fix is intentionally minimal and surgical: each change targets only the buggy code path and
preserves all retained behavior (section 3 of `bugfix.md`).

## Glossary

- **Bug_Condition (C)**: The condition that triggers a defect. Four sub-conditions C1–C4 (one per bug).
- **Property (P)**: The desired behavior once the bug condition holds (the fixed behavior).
- **Preservation**: Existing behavior that must remain identical after the fix (section 3 of `bugfix.md`).
- **`F` / `F'`**: The original (unfixed) / fixed function.
- **`StorageItem`**: `NamedTuple` in `services/storage_tracker.py` with fields
  `invoice_id, invoice_number, date_accepted_ms, days_stored, total_accepted, status`.
- **`FREE_DAYS`**: The existing `60`-day free-storage constant in `services/storage_tracker.py`
  (also `WARN_DAYS=53`, `ALERT_DAYS=57`, `PAID_DAYS=60`).
- **`free_days_left`**: `max(0, FREE_DAYS - days_stored)` — remaining free-storage days for an item.
- **`get_invoices(api_key, shop_id) -> list[dict]`**: Existing API call; returns `[]` on error/403.
- **`get_storage_alerts(items) -> dict`**: Existing grouping into `{"paid","alert","warn","ok"}`.
- **`price_source`**: Field on the competitor info dict: `"api" | "html" | "none"` (this design adds `"manual"`).
- **`CompetitorStates`**: `StatesGroup` in `handlers/main_menu.py` driving the competitor FSM flow.
- **`UZUM_PROXY`**: New env var holding an outbound proxy URL for `competitor_monitor` aiohttp GETs.
- **`_all_providers()`**: Builder in `services/gemini_ai.py` of configured AI providers (Groq → OpenRouter → Gemini).

## Bug Details

### Bug Condition

The four sub-conditions, formalized:

```
FUNCTION isBugCondition(input)
  INPUT: input — a user/runtime event
  OUTPUT: boolean

  // C1 — Storage free-days countdown missing
  C1 := input.action = "open_storage_view"
        AND invoices_are_computable(input.user)        // get_invoices + parse_invoices yield items
        AND NOT free_days_section_rendered(input)

  // C2 — Daily report still present
  C2 := (input.action = "render_main_menu" AND report_button_present(keyboard))
        OR (input.action = "tap_report_button" AND cmd_report_today_handler_reachable())

  // C3 — Competitor price not shown for a pasted Uzum URL
  C3 := input.action = "paste_uzum_url"
        AND auto_price_result.price_source = "none"      // OR min_price <= 0
        AND NOT (manual_fallback_offered OR proxy_configured OR localized_note_shown)

  // C4 — AI action with a valid key, read too early
  C4 := input.action = "ai_action"
        AND provider_key_present_in_dotenv()
        AND provider_env_read_at_import_time_before_load_dotenv()   // => _select_providers() == []

  RETURN C1 OR C2 OR C3 OR C4
END FUNCTION
```

### Examples

- **C1**: Seller with two ACCEPTED invoices (43 and 58 days stored) taps `🏭 Склад`. Expected: a
  free-storage section shows `60 - 43 = 17` and `60 - 58 = 2` days remaining (the 58-day item flagged
  as nearing the limit). Actual (unfixed): only stock groupings appear; no countdown.
- **C2**: User opens the main menu and still sees `📊 Отчёт`; tapping it runs `cmd_report_today` and
  produces a report that should no longer exist.
- **C3**: User pastes `https://uzum.uz/ru/product/suv-shari-2855035` from a Render (datacenter) IP.
  `api.uzum.uz` returns null payloads and the page returns captcha, so `get_product_info_by_url`
  returns `price_source == "none"`. Actual (unfixed): report shows no competitor price and no way forward.
- **C4**: `.env` has a valid `GROQ_API_KEY`. User taps `🤖 AI Совет`. Actual (unfixed): reply is
  "⚠️ AI не настроен …" because `GROQ_API_KEY` was read as `""` at import time (before `load_dotenv()`).
- **Edge (C1)**: `get_invoices` returns `[]` (no invoices or 403). Expected: stock view preserved + a
  localized note that free-storage data is unavailable; no crash.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors (must continue to work exactly as before — `bugfix.md` §3):**

- **Storage stock view (3.1-adjacent)**: The existing FBS stock groupings (out / low / warn / ok) must
  remain, with the free-days section added *alongside*, not replacing them.
- **Products (3.1)**: products listing, pagination, SKU display unchanged.
- **Orders (3.2)**: orders view, finance overlay, and the **inline** product-based 403 fallback that
  lives inside `cmd_orders` (it builds text inline; it does NOT call `report_fallback`) unchanged.
- **Finance (3.3)**: `get_finance_orders` / `summarize_finance_orders` usage unchanged.
- **Multi-shop (3.4)**, **charts (3.5)**, **scheduler jobs incl. returns/storage alerts/delivered (3.6)**,
  **`/ping` `/health` self-ping (3.7)** unchanged.
- **AI prompt builders (3.8)**: `build_sales_analysis_prompt`, `build_competitor_advice_prompt`,
  `build_storage_advice_prompt`, and the public `ask_gemini` name remain call-site compatible.
- **Competitor saved-list (3.9)**: `check_saved_urls` and the signatures of `get_product_info_by_url`
  / `format_single_product_report` remain unchanged.
- **Auto price path (3.9/C3)**: when auto price IS found (`price_source` in `{"api","html"}`), the
  existing report renders exactly as before — the manual fallback only triggers when no price is found.
- **AI provider selection semantics (3.8)**: `_select_providers` ordering (Groq → OpenRouter → Gemini),
  `AI_PROVIDER` override, no-key localized message, cross-provider fallback — all unchanged; only the
  *source* of the env values moves from import-time to call-time.

**Scope:** All inputs where `isBugCondition` is false (every retained feature in `bugfix.md` §3) must
produce byte-identical behavior to the original `F`.

> The desired *correct* behavior for the buggy inputs is defined in **Correctness Properties** below.

## Hypothesized Root Cause

**Bug 1 (Storage):** `cmd_storage` was written to render stock levels from `get_products` only and
never wired in the invoice/free-days path, even though `storage_tracker` already computes `days_stored`
and `format_storage_report` already computes `days_left = max(0, FREE_DAYS - days_stored)`. The data and
math exist; the handler simply never calls them.

**Bug 2 (Report):** `main_menu_keyboard` still emits `t("btn_report")` and `cmd_report_today` is still
registered on `F.text.in_(["📊 Hisobot", "📊 Отчёт"])`. Operationally the user "still sees" weekly/
monthly/returns because Telegram reply-keyboards are **client-cached until `/start` re-sends them** and
the prior branch may be undeployed — but those buttons are already gone from code; the daily Report is
the one still present in code.

**Bug 3 (Competitor):** Two compounding causes — (a) Uzum soft-blocks datacenter/cloud IPs (captcha +
geo), so from Render both `api.uzum.uz` and the HTML page yield no price (`price_source == "none"`);
(b) there is no outbound-proxy escape hatch and no manual entry path, so the user is dead-ended.

**Bug 4 (AI):** `services/gemini_ai.py` reads `GROQ_API_KEY`/`OPENROUTER_API_KEY`/`GEMINI_API_KEY`/
`AI_PROVIDER`/`*_MODEL` into module-level constants **at import time**. `main.py` imports the handlers
(which transitively import `gemini_ai`) on lines 11-13 and only calls `load_dotenv()` on line 16 —
*after* the import. So at read time the env is empty, the constants are `""`, and `_select_providers()`
returns `[]`, producing the "AI not configured" message.

## Correctness Properties

Property 1: Bug Condition — Storage Free-Days Countdown

_For any_ storage-view open where invoices are computable (C1 holds), the fixed `cmd_storage` SHALL
render a free-storage section derived from `parse_invoices`/`StorageItem`, showing
`free_days_left = max(0, FREE_DAYS - days_stored)` per invoice (or summarized) and flagging items
nearing/over the 60-day limit, in addition to the existing stock view; when invoices are empty/403 it
SHALL render the stock view plus a localized "free-storage data unavailable" note, without crashing.

**Validates: Requirements 2.1, 2.2**

Property 2: Bug Condition — Daily Report Removed

_For any_ main-menu render (C2), the fixed `main_menu_keyboard` SHALL emit exactly six buttons
(Products, Orders, Storage, Competitor, AI, Settings) with no Report/weekly/monthly/returns button, and
the `cmd_report_today` handler for `📊 Hisobot`/`📊 Отчёт` SHALL no longer exist.

**Validates: Requirements 2.3, 2.4**

Property 3: Bug Condition — Competitor Price Always Shown

_For any_ pasted Uzum URL where auto price is blocked (C3: `price_source == "none"` or `min_price <= 0`),
the fixed `competitor_url_received` SHALL prompt for a manual competitor price, persist the product via
`add_product_url`, and render `format_single_product_report` using the entered price as the competitor
price; and when `UZUM_PROXY` is set the `competitor_monitor` GETs SHALL route through that proxy.

**Validates: Requirements 2.5, 2.6, 2.7**

Property 4: Bug Condition — AI Reads Env At Call Time

_For any_ AI action where a provider key exists in the environment (C4), the fixed `_all_providers()`
SHALL read the provider env vars via `os.getenv` at call time, so `_select_providers()` returns the
configured provider(s) and `ask_gemini` returns a real completion (e.g. Groq
`llama-3.3-70b-versatile`) instead of the "AI not configured" message — even when the env is populated
*after* module import.

**Validates: Requirements 2.8, 2.9**

Property 5: Preservation — Retained Behavior Unchanged

_For any_ input where no bug condition holds (`¬C(X)`), the fixed bot SHALL produce the same result as
the original: storage stock groupings, products, orders + inline 403 fallback, finance, multi-shop,
charts, scheduler jobs, self-ping, the competitor auto-price path, `check_saved_urls`, the kept
signatures (`get_product_info_by_url`, `format_single_product_report`, the AI prompt builders,
`ask_gemini`), and the AI provider-selection ordering/override/fallback semantics.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10**

## Fix Implementation

### Fix 1 — Storage free-days countdown

**Files**: `handlers/main_menu.py` (`cmd_storage`), `locales/i18n.py`.

**`services/storage_tracker.py`** (read-only confirmation, no change needed): `FREE_DAYS = 60`,
`StorageItem.days_stored`, `StorageItem.total_accepted`, `StorageItem.invoice_number`, `parse_invoices`,
and `get_storage_alerts` already exist. `format_storage_report` already computes
`days_left = max(0, FREE_DAYS - days_stored)`. The fix reuses these; it introduces no new math in the
tracker.

**`handlers/main_menu.py::cmd_storage`** — after the existing `get_products` stock computation and
before the final `msg.edit_text`, add a free-storage block:

1. Import (module-level) `from services.uzum_api import get_invoices` and
   `from services.storage_tracker import parse_invoices, get_storage_alerts, FREE_DAYS`.
2. Fetch invoices defensively: `invoices = await get_invoices(user["api_key"], user["shop_id"])`
   (returns `[]` on 403/error — never raises here, but still guard inside the existing `try`).
3. `items = parse_invoices(invoices)`.
4. **When `items` is non-empty (C1 true path → Property 1):** build a free-storage summary section to
   prepend (or append) to the stock `text`:
   - Use `get_storage_alerts(items)` to bucket items.
   - For a compact summary, compute the minimum remaining free days across items
     (`min(max(0, FREE_DAYS - it.days_stored) for it in items)`) and a count of items in
     `paid`+`alert`+`warn` (nearing/over the limit).
   - List up to N (e.g. 5) most-urgent invoices (highest `days_stored` first) as
     `#{invoice_number}: {free_days_left} kun/дн. qoldi` with an icon (💸/🚨/⚠️/✅ matching the
     existing `format_storage_report` convention).
   - Localize all labels via new i18n keys (below). Keep the existing `storage_free_limit` /
     `storage_title` keys usable but add explicit free-days keys for clarity.
5. **When `items` is empty / invoices `[]` (C1 edge → Property 1 fallback):** append a localized note
   (new key `storage_free_unavailable`) under the existing stock view. No crash, no behavior change to
   the stock groupings.
6. The free-storage section is **additive**: the existing out/low/warn/ok stock blocks are emitted
   exactly as today (preservation).

**`locales/i18n.py`** — add new keys (uz+ru), without modifying `t()` or any existing key:
   - `storage_free_header` — section title, e.g. uz `"⏳ <b>Bepul saqlash (60 kun):</b>"`, ru
     `"⏳ <b>Бесплатное хранение (60 дней):</b>"`.
   - `storage_free_item` — per-invoice line template using `{icon} {invoice_number} {free_days_left} {qty}`.
   - `storage_free_summary` — summarized line, e.g. "min remaining `{min_left}` days, `{at_risk}` items nearing limit".
   - `storage_free_unavailable` — fallback note, e.g. uz `"ℹ️ Bepul saqlash ma'lumoti hozir mavjud emas."`,
     ru `"ℹ️ Данные о бесплатном хранении сейчас недоступны."`.

### Fix 2 — Remove daily Report

**Files**: `utils/keyboards.py`, `handlers/main_menu.py`; tests
`tests/test_menu_keyboard.py`, `tests/test_report_403_integration.py`.

**`utils/keyboards.py::main_menu_keyboard`**:
- Remove the `builder.button(text=t("btn_report", lang))` line.
- Resulting buttons (order preserved): Products, Orders, Storage, Competitor, AI, Settings — **6**.
- Change layout to `builder.adjust(2, 2, 2)` (three rows of two).
- Keep the function signature `(lang: str = "ru") -> ReplyKeyboardMarkup` and `resize_keyboard=True`.
- Leave `btn_report` (and `btn_weekly`/`btn_monthly`/`btn_returns`) in `i18n.py` — harmless unused keys;
  removing them is out of scope and other code/tests may still reference the labels.

**`handlers/main_menu.py`**:
- Delete the entire `cmd_report_today` handler (the `@router.message(F.text.in_(["📊 Hisobot", "📊 Отчёт"]))`
  block) and its `# ─── Bugungi hisobot ───` section.
- Remove the now-unused import
  `from handlers.report_fallback import (build_product_fallback_report, product_stats_available)`.
  Verified: `cmd_orders` builds its 403 fallback text **inline** and does NOT use these symbols, so the
  import is the only `main_menu.py` reference.
- No other handler references `cmd_report_today`.

**`handlers/report_fallback.py` — decision: KEEP.** Rationale: the module is pure (i18n-only, no I/O),
is exercised directly by `tests/test_report_fallback.py` (builder, predicate, i18n keys, a PBT), and
deleting it would force deleting those passing tests for no functional gain. We simply stop importing it
from `main_menu.py`. This is documented here so a future reader knows the module is intentionally
retained as a tested utility even though no handler currently calls it.

**Tests to update:**
- `tests/test_menu_keyboard.py`: change `CORE_KEYS` to the six retained keys (drop `btn_report`), change
  the "exactly core buttons" assertion to the 6-button list, and change the layout assertion from
  `== 7` to `== 6`. (The analytics-router assertions are unaffected.)
- `tests/test_report_403_integration.py`: the three tests drive `mm.cmd_report_today`, which is being
  removed. Remove the daily-report tests (and the daily-only sample wiring) — the orders-present and
  non-403 preservation behavior for `cmd_orders` is already covered elsewhere; if desired, retarget the
  preservation intent onto `cmd_orders`. Document the removal in the file/test docstring.

**Operational note (not a code change):** the reason users still saw weekly/monthly/returns is
reply-keyboard client caching plus an unmerged/undeployed branch. The code-side fix is correct removal;
the operational fix is redeploy + the user pressing `/start` to receive the refreshed keyboard.

### Fix 3 — Competitor price: proxy + manual fallback

**Files**: `services/competitor_monitor.py`, `handlers/main_menu.py`, `locales/i18n.py`, `.env.example`.

**`services/competitor_monitor.py` — proxy support (call-time read):**
- In `_fetch_product_html(url)`: read `proxy = os.getenv("UZUM_PROXY", "") or None` at call time
  (`import os` at module top) and pass `proxy=proxy` to `session.get(...)`.
- In `_get_product_from_api(product_id)`: same — read `proxy` once at the start of the call and pass
  `proxy=proxy` to each `session.get(...)`.
- aiohttp accepts `proxy=None` as "no proxy", so behavior is unchanged when `UZUM_PROXY` is unset
  (preservation). No signature changes; `get_product_info_by_url` / `check_saved_urls` unchanged.

**`.env.example`** — document the new var (no secrets), e.g.:
```
# Optional: route Uzum scraping through a UZ/residential proxy so price fetch works from cloud IPs.
# Example: http://user:pass@host:port  (leave empty to fetch directly)
UZUM_PROXY=
```

**`handlers/main_menu.py` — manual fallback FSM flow:**
- Add a state to `CompetitorStates`: `waiting_manual_price = State()`.
- In `competitor_url_received`, after `info = await get_product_info_by_url(url)` and after the existing
  `add_product_url` save + `my_price` lookup, inspect the price:
  - **Auto price found** (`info.get("price_source") in {"api","html"}` and `min_price > 0`): render
    `format_single_product_report(...)` exactly as today and `state.clear()` (preservation path).
  - **No auto price** (`price_source == "none"` or `min_price <= 0` → Property 3): store the pending
    product in FSM data
    `await state.update_data(pending_name=product_name_short, pending_url=url, my_price=my_price)`,
    set `await state.set_state(CompetitorStates.waiting_manual_price)`, and send a localized note +
    manual-entry prompt (new i18n keys). Do **not** clear state.
- Add a new handler `@router.message(CompetitorStates.waiting_manual_price)`:
  1. Parse the number from `message.text` (strip spaces/separators; reject non-numeric or `<= 0` with a
     localized re-prompt, staying in the same state).
  2. Read FSM data (`pending_name`, `pending_url`, `my_price`).
  3. Persist via the already-used `add_product_url(user_id, shop_id, product_name=pending_name,
     uzum_url=pending_url)` (idempotent re-save is acceptable; or rely on the save already done in
     `competitor_url_received`).
  4. Build a competitor-info dict and render the report:
     `info = {"title": pending_name, "min_price": manual_price, "max_price": manual_price,
     "price_source": "manual", "html_only": False, "shop": "—", "rating": 0, "reviews": 0}` and call
     `format_single_product_report(pending_name, my_price, info, lang)`. The manually entered value is
     treated as the competitor (market) price; `format_single_product_report` then renders the
     min/max/my-price comparison using its existing logic (signature unchanged).
  5. `await state.clear()`.
- Handle the `🔙 Назад / 🔙 Orqaga` cancel text in the manual-price handler the same way
  `competitor_url_received` does (clear state and return).

**`locales/i18n.py`** — add new keys (uz+ru), no `t()`/existing-key changes:
   - `competitor_blocked_note` — explains auto price is unavailable due to IP blocking and that a UZ
     IP/proxy is required. uz e.g. `"⚠️ Avtomatik narx olinmadi (Uzum cloud IP larни bloklaydi). UZ IP/proxy kerak."`;
     ru e.g. `"⚠️ Автоцена недоступна (Uzum блокирует облачные IP). Нужен UZ IP/прокси."`
   - `competitor_manual_prompt` — asks the user to type the competitor price manually. uz e.g.
     `"✍️ Raqobatchi narxini qo'lda kiriting (faqat raqam, so'mda):"`; ru e.g.
     `"✍️ Введите цену конкурента вручную (только число, в сумах):"`
   - `competitor_manual_invalid` — re-prompt on bad input. uz e.g. `"❌ Noto'g'ri qiymat. Faqat musbat raqam yuboring."`;
     ru e.g. `"❌ Неверное значение. Отправьте только положительное число."`

### Fix 4 — AI env read at call time

**File**: `services/gemini_ai.py`.

- **Remove** the module-level constant assignments `GROQ_API_KEY = os.getenv(...)`,
  `OPENROUTER_API_KEY`, `GEMINI_API_KEY`, `AI_PROVIDER`, `GROQ_MODEL`, `OPENROUTER_MODEL`,
  `GEMINI_MODEL`.
- **Inside `_all_providers()`** read them lazily via `os.getenv` at call time:
  ```
  groq_key   = os.getenv("GROQ_API_KEY", "")
  or_key     = os.getenv("OPENROUTER_API_KEY", "")
  gem_key    = os.getenv("GEMINI_API_KEY", "")
  groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
  or_model   = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")
  gem_model  = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
  ```
  Build the `ProviderConfig`s from these locals. Groq endpoint stays
  `https://api.groq.com/openai/v1/chat/completions` (confirmed working with
  `llama-3.3-70b-versatile`).
- **`_select_providers()`** must also read `AI_PROVIDER` at call time:
  `provider = os.getenv("AI_PROVIDER", "").strip().lower()` (it currently reads the module constant).
  Its ordering/override/empty-list logic is otherwise unchanged.
- `ask_gemini`, `_call_openai_compatible`, `_call_gemini`, the prompt builders, and `SSL_CONTEXT`
  are unchanged.
- **Defense-in-depth (optional)**: add `from dotenv import load_dotenv` and call `load_dotenv()` once
  near the top of `gemini_ai.py`. The primary, required fix is the call-time read; `load_dotenv()` here
  is a belt-and-suspenders measure and is safe (idempotent).

**Test impact (must update):** `tests/test_ai_providers.py` currently monkeypatches the **module-level
constants** (`monkeypatch.setattr(g, "GROQ_API_KEY", ...)`). Once those constants are removed and values
are read via `os.getenv`, those monkeypatches no longer influence selection. Update the test helper to
set the **environment** instead — `monkeypatch.setenv("GROQ_API_KEY", ...)` / `monkeypatch.delenv(...,
raising=False)` (and likewise for the other keys and `AI_PROVIDER`). The assertions
(ordering, override, no-key message, fallback dispatch) stay the same.

## Testing Strategy

### Validation Approach

Two phases per bug: first surface counterexamples on the **UNFIXED** code (exploration), then verify the
fix works and that preservation tests still pass. Property-based tests are used where the property is
universal (price-extraction threshold, preservation across non-buggy inputs); example/scoped tests are
used for deterministic, environment-driven defects (AI env read, keyboard shape).

### Exploratory Bug Condition Checking

**Goal**: Demonstrate each bug exists before fixing. Confirm/refute the root-cause hypotheses.

**Test plan & cases**:
1. **Storage (C1)** — call `cmd_storage` with `get_invoices` mocked to return two ACCEPTED invoices
   (e.g. 43 & 58 days stored) and assert the rendered text contains free-days values (`17`, `2`). On
   UNFIXED code this FAILS (no free-days section). Scope to concrete invoices for reproducibility.
2. **Menu (C2)** — assert `main_menu_keyboard("ru")`/`("uz")` yields exactly 6 buttons and no Report
   label, and that `handlers.main_menu` has no `cmd_report_today`. On UNFIXED code this FAILS (7 buttons,
   handler present).
3. **Competitor (C3)** — drive `competitor_url_received` with `get_product_info_by_url` mocked to return
   `price_source == "none"`; assert the bot transitions to `waiting_manual_price` and prompts for manual
   entry. On UNFIXED code this FAILS (no such state/handler).
4. **AI (C4)** — clear all provider env vars, import `gemini_ai`, then `os.environ["GROQ_API_KEY"]="x"`
   *after* import, and assert `_select_providers()` is non-empty. On UNFIXED code this FAILS (module
   constant captured `""` at import; selection empty).

**Expected counterexamples**: storage view with no countdown; 7-button keyboard with `📊 Отчёт`;
dead-ended competitor flow; empty provider list despite a populated env.

### Fix Checking

**Goal**: For all inputs where the bug condition holds, the fixed function produces the expected behavior.

```
FOR ALL input WHERE isBugCondition(input) DO
  result := fixedFunction(input)
  ASSERT expectedBehavior(result)   // Properties 1-4
END FOR
```

**Concrete fix tests:**
- **Storage free-days unit test** — given mocked invoices, assert `cmd_storage` renders
  `free_days_left = max(0, 60 - days_stored)` per invoice and flags the near-limit item; given
  `get_invoices -> []`, assert the stock view + `storage_free_unavailable` note render without raising.
- **Keyboard has 6 buttons, no Report** — `main_menu_keyboard` returns exactly the six core labels in
  order for uz+ru, layout sums to 6, and none of report/weekly/monthly/returns labels appear; assert
  `not hasattr(handlers.main_menu, "cmd_report_today")`.
- **AI picks up env set AFTER import** — with env cleared at import, set `os.environ` (e.g.
  `GROQ_API_KEY`) and assert `_select_providers()` returns `["groq"]` and a stubbed
  `_call_openai_compatible` makes `ask_gemini` return a real answer (not the "not configured" message).
  Also verify `AI_PROVIDER` override read at call time.
- **Competitor manual fallback** — drive `competitor_url_received` (mock `get_product_info_by_url` →
  `price_source="none"`) to enter `waiting_manual_price`; then drive the new handler with a numeric
  message and assert it calls `add_product_url` and that `format_single_product_report` is rendered with
  the entered value as the competitor (min/max) price; assert a non-numeric input re-prompts and stays
  in state.
- **Proxy param passed when `UZUM_PROXY` set** — monkeypatch `os.environ["UZUM_PROXY"]`, stub the
  aiohttp session, and assert `session.get` receives `proxy="<value>"` in both `_fetch_product_html`
  and `_get_product_from_api`; assert `proxy=None` is passed when unset.

### Preservation Checking

**Goal**: For all inputs where the bug condition does NOT hold, the fixed function equals the original.

```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT originalFunction(input) = fixedFunction(input)
END FOR
```

**Testing approach**: property-based testing is recommended for preservation because it covers many
inputs and catches edge cases. Observe behavior on UNFIXED code first, then assert it is unchanged.

**Test plan & cases (observation-first):**
1. **Competitor auto-price preserved** — when `get_product_info_by_url` returns `price_source` in
   `{"api","html"}` with `min_price > 0`, the existing single-product report renders and state clears
   exactly as before; manual fallback does NOT trigger. (Existing `tests/test_competitor_price.py`
   Property 6/7 continue to pass; resolver and `format_single_product_report` signatures unchanged.)
2. **Proxy-off equivalence** — with `UZUM_PROXY` unset, `competitor_monitor` GETs behave identically
   to today (`proxy=None`).
3. **AI selection semantics preserved** — ordering (Groq → OpenRouter → Gemini), `AI_PROVIDER` override,
   no-key localized message, and cross-provider fallback all unchanged (existing `tests/test_ai_providers.py`
   retargeted to env-based monkeypatching still pass).
4. **Storage stock groupings preserved** — out/low/warn/ok blocks render identically when the free-days
   section is added.
5. **Orders inline 403 fallback preserved** — `cmd_orders` behavior (orders present, finance overlay,
   product-based inline fallback) unchanged after `cmd_report_today` removal.
6. **report_fallback utility preserved** — `tests/test_report_fallback.py` (builder/predicate/i18n/PBT)
   continues to pass since the module is retained.

### Unit Tests

- Storage free-days computation (per-invoice and `[]`/403 fallback note).
- `main_menu_keyboard` shape: 6 buttons, correct order, no Report.
- `gemini_ai` env-at-call-time selection and `ask_gemini` success/no-key/fallback (env-based patching).
- Competitor manual-fallback handler: state transition, numeric parse, save, render; invalid re-prompt.
- Proxy parameter forwarding in both competitor GET helpers.

### Property-Based Tests

- Existing price-extraction PBTs in `tests/test_competitor_price.py` (threshold, min/max) remain valid.
- Existing `report_fallback` builder PBT remains valid.
- (Optional) Preservation PBT: for random non-buggy competitor `info` dicts with a valid price, the
  manual fallback is never entered and the auto report is rendered.

### Integration Tests

- End-to-end competitor flow: paste URL → (blocked) → manual prompt → enter price → report shown.
- Main-menu render → tap each of the six retained buttons routes to its handler (no Report route).
- Storage view with invoices present shows both the free-days section and the stock groupings.
