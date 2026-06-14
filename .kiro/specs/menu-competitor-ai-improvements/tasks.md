# Implementation Plan: Menu / Competitor / AI Improvements

## Overview

This plan implements three independent, locally-scoped changes to the **Uzumchi** bot (Python 3.11, aiogram 3) in the design's recommended order: **Change 1** (menu cleanup) → **Change 3** (multi-provider AI) → **Change 2** (competitor HTML price). Every public function name consumed by handlers is preserved, so call sites stay untouched. All work is confined to `/projects/sandbox/Uzumchi`; `uzum_seller_bot/` is read-only reference and is never edited.

Language: **Python** (matches the existing codebase and the design's low-level pseudocode). Property tests use **hypothesis** (already present — see `.hypothesis/`); unit/integration tests use the existing `pytest` setup under `tests/`.

Each task references the requirement clauses and/or correctness properties it satisfies. Sub-tasks marked with `*` are optional (tests) and are not auto-implemented.

## Tasks

- [x] 1. CHANGE 1 — Trim the main menu keyboard
  - [x] 1.1 Reduce `main_menu_keyboard` to the 7 Core_Menu_Buttons
    - Edit `utils/keyboards.py`: remove the three `builder.button(... btn_weekly / btn_monthly / btn_returns ...)` lines so only Products, Orders, Storage, Report, Competitor, AI, Settings remain
    - Change the layout call to `builder.adjust(2, 2, 2, 1)` (rows sum to 7)
    - Keep the `main_menu_keyboard(lang: str = "ru")` signature unchanged
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 7.5_

  - [x]* 1.2 Write unit test for menu button set and layout
    - In `tests/`, add a test that calls `main_menu_keyboard("uz")` and `main_menu_keyboard("ru")` and asserts the rendered button texts equal the Core_Menu_Buttons and contain none of `btn_weekly`/`btn_monthly`/`btn_returns` labels in either language
    - Assert the keyboard renders 7 buttons (layout rows sum to 7)
    - **Property 1: Keyboard exclusivity** and **Property 2: Keyboard layout validity**
    - **Validates: Requirements 1.1, 1.2, 1.3**

- [x] 2. CHANGE 1 — Remove Weekly/Monthly/Returns handlers and dead code from analytics
  - [x] 2.1 Delete the removed-section handlers and now-dead helpers in `handlers/analytics.py`
    - Remove handlers `cmd_weekly` (`F.text.in_(["📈 Haftalik", "📈 Недельный"])`), `cmd_monthly` (`["📅 Oylik", "📅 Месячный"]`), and `cmd_returns` (`["↩️ Qaytarmalar", "↩️ Возвраты"]`)
    - Remove the dead module-level helpers `_build_daily_data(...)` and `_is_in_week(...)`
    - Remove the `report_fallback` import (`build_product_fallback_report`, `product_stats_available`) and `import datetime` (only used by removed code)
    - Keep all AI_Handlers (`cmd_ai`, `ai_sales_analysis`, `ai_storage_advice`, `ai_question_start`, `ai_question_process`, `ai_back`), the `AIStates` group, and `router`
    - _Requirements: 2.1, 2.2, 2.4_

  - [x] 2.2 Reconcile the import block to only names the retained AI handlers use
    - Trim `services.uzum_api` import to `get_fbs_orders_period, get_products, get_invoices, summarize_orders`; drop `get_returns, get_expenses, get_finance_orders, summarize_finance_orders, get_sales_stats_from_products, _days_ago_ms, _now_ms`
    - Trim `services.storage_tracker` import to `parse_invoices`; drop `get_storage_alerts`
    - Keep `ask_gemini, build_sales_analysis_prompt, build_storage_advice_prompt` from `services.gemini_ai`
    - Trim keyboards import to `main_menu_keyboard, ai_keyboard, cancel_keyboard` (drop `back_keyboard`); drop the entire `utils.helpers` import
    - Verify the final list against the actual kept-handler bodies (remove any unused name, add back any used name) per the design's import audit
    - _Requirements: 2.3, 2.5_

  - [x]* 2.3 Write router integrity test for `handlers/analytics.py`
    - Add a test that does `import handlers.analytics` and asserts no `ImportError`/`NameError` is raised
    - Assert `router` still registers the AI handlers and that `cmd_weekly`/`cmd_monthly`/`cmd_returns` names are absent from the module
    - **Property 3: Analytics router integrity**
    - **Validates: Requirements 2.1, 2.3, 2.4, 2.5**

  - [x] 2.4 Remove the obsolete weekly/monthly integration tests
    - In `tests/test_report_403_integration.py`, delete the four functions that drive the deleted handlers: `test_weekly_fallback_on_403_orders`, `test_weekly_orders_present_unchanged`, `test_monthly_fallback_on_403_orders`, `test_monthly_orders_present_unchanged`
    - Keep the three **daily** report tests (`cmd_report_today` in `handlers/main_menu.py`) intact and passing
    - _Requirements: 2.1, 6.2_

- [x] 3. Checkpoint — menu cleanup verified
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. CHANGE 3 — Multi-provider AI layer in `services/gemini_ai.py`
  - [x] 4.1 Add provider configuration and selection
    - In `services/gemini_ai.py`, read `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`, `AI_PROVIDER`, and the per-provider `*_MODEL` env vars
    - Add the frozen `ProviderConfig` dataclass (`name`, `api_key`, `endpoint`, `model`, `kind`)
    - Implement `_all_providers()` (only includes a provider when its key is non-empty) and `_select_providers()` (Groq → OpenRouter → Gemini order; `AI_PROVIDER` override returns exactly that one when its key is set; empty list when nothing configured)
    - _Requirements: 4.1, 4.2, 5.1, 5.2_

  - [x]* 4.2 Write property/unit test for provider selection ordering and override
    - Use `monkeypatch` to set/clear env vars; assert default order is Groq→OpenRouter→Gemini filtered to configured keys
    - Assert `AI_PROVIDER` naming an available provider returns exactly `[that provider]`; assert empty list when no key configured
    - Assert a non-`AIzaSy`-prefixed key is still accepted as usable
    - **Property 8: Provider ordering** and **Property 11: Key-format liberty**
    - **Validates: Requirements 4.1, 4.2, 5.1, 5.2**

  - [x] 4.3 Implement the provider call helpers
    - Add `_call_openai_compatible(cfg, prompt)` (shared Groq/OpenRouter chat-completions schema, default TLS, 30s timeout)
    - Add `_call_gemini(cfg, prompt)` (`generateContent` v1beta, key as query param, permissive `SSL_CONTEXT`)
    - On non-200, log status code and response body (first ~300 chars) without ever logging the API key, then raise to trigger fallback
    - _Requirements: 4.6_

  - [x] 4.4 Rewrite `ask_gemini` as provider-agnostic dispatch
    - Remove the `if not GEMINI_API_KEY.startswith("AIzaSy")` format-check block
    - Build the ordered provider list via `_select_providers()`; if empty, return the localized "AI not configured" message (uz/ru) and perform **no** network call
    - Iterate providers: dispatch by `cfg.kind`, return first non-empty answer; on failure/empty log and continue to next; return localized error if all fail
    - Keep `ask_gemini(prompt, lang="ru")` signature and the three prompt builders (`build_sales_analysis_prompt`, `build_storage_advice_prompt`, `build_competitor_advice_prompt`) unchanged
    - _Requirements: 4.3, 4.4, 4.5, 4.7, 4.8, 5.3, 5.4, 7.1, 7.2_

  - [x]* 4.5 Write dispatch tests with mocked HTTP
    - Mock the aiohttp session; assert success path returns the first provider's answer
    - Assert fallback: first provider raises/empty → next configured provider is attempted and its answer returned
    - Assert no-key behavior returns a non-empty localized message and makes **no** HTTP call
    - Assert all-providers-fail returns a non-empty localized error
    - **Property 9: No-key behavior** and **Property 10: Fallback dispatch**
    - **Validates: Requirements 4.3, 4.4, 4.5, 5.3, 5.4**

  - [x] 4.6 Document AI provider env vars in `.env.example`
    - Replace the existing `GEMINI_API_KEY=` line with the block documenting `GROQ_API_KEY`/`GROQ_MODEL`, `OPENROUTER_API_KEY`/`OPENROUTER_MODEL`, `GEMINI_API_KEY`/`GEMINI_MODEL`, and `AI_PROVIDER` (with priority note Groq → OpenRouter → Gemini)
    - _Requirements: 4.1, 5.1_

- [x] 5. Checkpoint — AI advisor verified
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. CHANGE 2 — HTML price extraction in `services/competitor_monitor.py`
  - [x] 6.1 Add the pure price-extraction helpers
    - In `services/competitor_monitor.py`, add `get_price_from_html(html) -> tuple[float, float] | None` parsing JSON-LD `offers` (`price`/`lowPrice`/`highPrice`) and embedded state keys (`sellPrice`, `purchasePrice`, `minSellPrice`, `price`, `fullPrice`)
    - Add `_accumulate_price(value, prices)` that coerces to float and only appends values `> 100` (Price_Threshold)
    - Return `(min(prices), max(prices))` or `None` when no qualifying price exists
    - _Requirements: 3.2, 3.3, 3.4_

  - [x]* 6.2 Write property test for price extraction soundness and threshold
    - Use `hypothesis` to synthesize HTML from float lists: for values `> 100`, assert result is `(min(values), max(values))`; assert no value `<= 100` appears in the result; assert `None` when no qualifying value
    - Add example-based fixtures: a JSON-LD `offers` block and an embedded `"sellPrice"` block (`> 100` threshold)
    - **Property 4: Price extraction soundness** and **Property 5: Price threshold**
    - **Validates: Requirements 3.2, 3.3, 3.4**

  - [x] 6.3 Refactor HTML fetch and title parsing
    - Add `_fetch_product_html(url) -> str | None` (single GET, permissive `SSL_CONTEXT`, `HTML_HEADERS`, 15s timeout, returns `None` and logs on error/non-200)
    - Extract the existing title-parsing logic into pure `_title_from_html(html) -> str | None`
    - Make `get_product_title_from_html(url)` a thin wrapper calling `_fetch_product_html` then `_title_from_html`
    - _Requirements: 3.9_

  - [x] 6.4 Wire HTML price into `get_product_info_by_url`
    - Fetch HTML once; derive `title_from_html` and `html_prices`
    - When API returns a payload with `min_price > 0`, keep API price and set `price_source="api"` (do not overwrite with HTML)
    - When API has no usable/positive price but HTML yields a price, populate `min_price`/`max_price`/`price` from HTML and set `price_source="html"`, `html_only=False`
    - When neither yields a price, set `price_source="none"` and `html_only=True`
    - Always include `min_price`, `max_price`, `price_source`, `url`; keep the `get_product_info_by_url` signature unchanged; never raise to the handler
    - _Requirements: 3.1, 3.5, 3.6, 3.7, 3.9, 3.10, 7.3_

  - [x]* 6.5 Write unit tests for resolver price-source selection
    - Mock `_get_product_from_api` and `_fetch_product_html`: assert API-with-price → `price_source="api"` (HTML not used); API-null + HTML price → `price_source="html"` with HTML min/max; neither → `price_source="none"`, `html_only=True`
    - Assert errors during fetch/parse are handled internally (no exception propagates)
    - **Property 6: API-preserves-when-present**
    - **Validates: Requirements 3.1, 3.5, 3.6, 3.7, 3.9**

  - [x]* 6.6 Write test that the report renders the price block when a price exists
    - Build an `info` dict with `min_price > 0` (once for `price_source="api"`, once for `"html"`) and assert `format_single_product_report` output contains the price/Narxlar/Цены block in both cases
    - Confirm `format_single_product_report` signature is unchanged
    - **Property 7: Report shows price when available**
    - **Validates: Requirements 3.8, 3.10, 7.4**

- [x] 7. Final checkpoint — full preservation and integration check
  - [x]* 7.1 Add an import smoke test for full app wiring
    - Add a test that `import main` succeeds (transitively imports all routers + scheduler) and that the Analytics_Router is registered with its AI handlers
    - **Property 3** and **Property 12: Preservation**
    - **Validates: Requirements 2.6, 6.9**

  - [x] 7.2 Run the full test suite and confirm preservation
    - Run `pytest tests/ --run`-style single execution; confirm daily report (incl. 403 product-fallback), finance overlay, `check_saved_urls`, scheduler, charts, and health tests still pass unchanged
    - Ensure all tests pass, ask the user if questions arise.
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_

## Notes

- Tasks marked with `*` are optional (tests) and can be skipped for a faster MVP; core implementation tasks are never optional.
- The model MUST NOT implement `*`-postfixed sub-tasks automatically.
- Each task references specific requirement clauses and/or correctness properties for traceability.
- `locales/i18n.py` is intentionally **not** edited (keys kept to avoid churn and to keep `tests/test_i18n.py` passing) — this is a documented design decision, so it has no task.
- `handlers/main_menu.py`, `services/scheduler.py`, `services/uzum_api.py`, and `main.py` require no source edits; they are validated by the checkpoint/smoke tests only.
- Property tests use `hypothesis`; no new third-party dependencies are introduced (`aiohttp` already covers all network calls).

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "4.1", "6.1"] },
    { "id": 1, "tasks": ["1.2", "2.1", "4.2", "4.3", "6.2", "6.3"] },
    { "id": 2, "tasks": ["2.2", "4.4", "6.4"] },
    { "id": 3, "tasks": ["2.3", "2.4", "4.5", "4.6", "6.5", "6.6"] },
    { "id": 4, "tasks": ["7.1"] },
    { "id": 5, "tasks": ["7.2"] }
  ]
}
```
