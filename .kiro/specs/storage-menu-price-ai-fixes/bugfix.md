# Bugfix Requirements Document

## Introduction

This spec fixes four reported defects observed on the running Uzumchi Telegram bot. Scope is **strictly the `/projects/sandbox/Uzumchi` repository**; `uzum_seller_bot` is read-only reference and MUST NOT be modified.

1. **Storage view lacks free-storage-days countdown** — the "🏭 Ombor"/"🏭 Склад" view shows only stock levels and never tells the seller how many of Uzum's 60 free storage days remain, even though the data and logic to compute it already exist (`services/storage_tracker.py` + `get_invoices`).
2. **Report sections still appear** — Отчёт (daily), Недельный, Месячный and Возвраты must all be gone, but the daily Отчёт ("📊 Hisobot"/"📊 Отчёт") button and its `cmd_report_today` handler are still present.
3. **Competitor price not shown for a pasted Uzum URL** — Uzum blocks datacenter/cloud IPs (captcha + geo soft-block) and product pages are JS-rendered SPAs, so a cloud host (e.g. Render) cannot fetch a price; the user is left with no comparison.
4. **AI Совет doesn't work despite a valid Groq key** — provider env vars are read at module-import time, but `main.py` calls `load_dotenv()` *after* importing the handlers (which import `gemini_ai`), so the keys are empty when read and the bot replies "AI not configured".

Each bug below is captured with the condition that triggers it, the current (defective) behavior, the expected (correct) behavior, and the behavior that must be preserved.

## Bug Analysis

### Current Behavior (Defect)

**Bug 1 — Storage free-days countdown missing**

1.1 WHEN the user taps "🏭 Ombor"/"🏭 Склад" THEN the system shows only stock-level groupings (out / low / warning / ok from `products`/`skuList`) and does NOT show any free-storage-days-remaining information.

1.2 WHEN invoice data is available for the user (via `get_invoices` + `parse_invoices`) THEN the storage view still ignores it and never surfaces the per-invoice/summarized free-days-left countdown (`60 - days_stored`).

**Bug 2 — Report sections still present**

1.3 WHEN the user opens the main menu THEN the daily report button ("📊 Hisobot"/"📊 Отчёт") is still rendered by `main_menu_keyboard`, so the user can still see/trigger a report section that should have been removed.

1.4 WHEN the user taps the daily report button THEN the `cmd_report_today` handler still runs and produces a report, instead of the feature being absent.

**Bug 3 — Competitor price not shown for a pasted URL**

1.5 WHEN the user pastes an Uzum product URL and the bot runs from a datacenter/cloud IP THEN `api.uzum.uz` returns null payloads and product pages return captcha, so auto price fetch yields no price and the comparison report shows no competitor price.

1.6 WHEN auto price fetch returns no price THEN the system does NOT offer any way to continue, so the user is left without any price comparison result.

1.7 WHEN the operator wants automatic fetching to work from a UZ/residential network THEN there is no supported outbound proxy configuration, and there is no localized note explaining why the automatic price is unavailable.

**Bug 4 — AI Совет not working with a valid Groq key**

1.8 WHEN the user taps "🤖 AI Maslahat"/"🤖 AI Совет" (or any AI action) and a valid `GROQ_API_KEY` exists in `.env` THEN `ask_gemini` replies with the localized "AI not configured" message (or no real answer) instead of a completion.

1.9 WHEN the process starts THEN `services/gemini_ai.py` reads provider env vars (`GROQ_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`, `AI_PROVIDER`, `*_MODEL`) at module-import time — before `main.py` calls `load_dotenv()` (which runs after importing the handlers that import `gemini_ai`) — so the keys are read as empty and `_select_providers()` returns an empty list.

### Expected Behavior (Correct)

**Bug 1 — Storage free-days countdown**

2.1 WHEN the user taps "🏭 Ombor"/"🏭 Склад" and invoices are available THEN the system SHALL show the remaining free-storage days (`60 - days_stored`) per item/invoice or as a summarized countdown, in addition to the stock view.

2.2 WHEN invoices are unavailable (empty result or 403) THEN the system SHALL keep the existing stock-level view and add a localized (uz+ru) note that the free-storage-days countdown is unavailable, without crashing.

**Bug 2 — Report sections removed**

2.3 WHEN the user opens the main menu THEN `main_menu_keyboard` SHALL show exactly six buttons: Products, Orders, Storage, Competitor, AI, Settings — with no daily/weekly/monthly report or returns buttons.

2.4 WHEN the daily report text ("📊 Hisobot"/"📊 Отчёт") is sent THEN the system SHALL NOT have a `cmd_report_today` handler for it; the handler and any now-dead report wiring (including unused report 403 product-fallback wiring) SHALL be removed.

**Bug 3 — Competitor price comparison reliably visible**

2.5 WHEN the `UZUM_PROXY` environment variable is set THEN `competitor_monitor` fetches SHALL route outbound requests through that proxy (aiohttp `proxy=`), so a UZ proxy makes automatic price fetching work.

2.6 WHEN automatic price fetch returns no price (blocked/null) THEN the system SHALL prompt the user to enter the competitor's price manually, save it, and show the comparison report (my price vs entered competitor price) so the user always sees a result.

2.7 WHEN the automatic price is unavailable due to IP blocking THEN the system SHALL display a clear localized (uz+ru) note explaining that automatic price retrieval requires a UZ IP/proxy.

**Bug 4 — AI Совет works at runtime**

2.8 WHEN the user triggers an AI action and a provider key is present in `.env` THEN `gemini_ai` SHALL read the provider env vars (`GROQ_API_KEY`/`OPENROUTER_API_KEY`/`GEMINI_API_KEY`/`AI_PROVIDER`/`*_MODEL`) at call time — inside `_all_providers()`/`_select_providers()` — rather than at import time, so the key is picked up at runtime.

2.9 WHEN a valid `GROQ_API_KEY` is configured THEN `ask_gemini` SHALL return a real Groq completion instead of the "AI not configured" message.

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the user uses Products THEN the system SHALL CONTINUE TO show products, pagination, and SKU display unchanged.

3.2 WHEN the user uses Orders THEN the system SHALL CONTINUE TO show orders, finance overlays, and the existing daily 403 product-based fallback handling that remains relevant.

3.3 WHEN finance functions are used elsewhere (orders view, scheduler) THEN they SHALL CONTINUE TO work unchanged.

3.4 WHEN a user has multiple shops THEN multi-shop selection and switching SHALL CONTINUE TO work unchanged.

3.5 WHEN charts are generated THEN chart functionality SHALL CONTINUE TO work unchanged.

3.6 WHEN the scheduler runs THEN all scheduled jobs (including `run_returns_check` and `get_returns`, storage alerts, delivered notifications) SHALL CONTINUE TO work unchanged.

3.7 WHEN `/ping` or `/health` is called, or the self-ping keep-alive runs THEN they SHALL CONTINUE TO work unchanged.

3.8 WHEN the AI prompt builders are used THEN `build_sales_analysis_prompt`, `build_competitor_advice_prompt`, `build_storage_advice_prompt` and the public `ask_gemini` name SHALL CONTINUE TO work and remain call-site compatible.

3.9 WHEN the user opens the competitor saved-URL list THEN the saved-list view (`check_saved_urls`) and the signatures of `get_product_info_by_url` / `format_single_product_report` SHALL CONTINUE TO work unchanged.

3.10 WHEN any input does NOT involve keyboard input affected by these fixes (e.g. mouse-equivalent button taps for retained features, other commands) THEN the system SHALL CONTINUE TO behave exactly as before the fix.

---

## Notes (operational, non-code)

- **Bug 2 "still seeing them":** The likely operational cause of weekly/monthly/returns still appearing is that the prior PR branch is unmerged/undeployed AND Telegram reply keyboards are client-cached until `/start` re-sends them. This is captured as a note, not a code requirement — the code requirement is that the keyboard and daily-report handler be removed (2.3, 2.4).
- **Bug 4 optional hardening:** Ensuring `load_dotenv()` runs early is acceptable as an additional safeguard, but the required fix is the call-time env read (2.8).

## Bug Condition Summary

For traceability into design, the bug condition C(X) for each defect:

- **C1 (Storage):** `input = open storage view` AND `invoices computable` AND `free-days countdown not shown`.
- **C2 (Menu):** `input = render main menu` AND (`report/weekly/monthly/returns button present` OR `cmd_report_today handler reachable`).
- **C3 (Competitor):** `input = pasted Uzum URL` AND `auto price fetch returns no price` AND `no manual fallback / proxy / note offered`.
- **C4 (AI):** `input = AI action` AND `provider key present in .env` AND `provider env read at import time before load_dotenv` ⇒ `_select_providers()` empty.

Non-buggy inputs `¬C(X)` (all retained features in section 3) must be preserved: the fixed bot SHALL behave identically to the original for them.
