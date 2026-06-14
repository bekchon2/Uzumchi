# Requirements Document

## Introduction

This document specifies the requirements for three independent, user-requested improvements to the working **Uzumchi** Telegram bot (aiogram 3, Python 3.11, SQLite, APScheduler). The requirements are derived from the already-approved design document and follow its guiding principle of **maximum behavior preservation with minimal blast radius**.

The three changes are:

1. **Menu cleanup** — remove the Weekly, Monthly, and Returns sections from the main menu and clean up their handler code, while keeping every other capability intact.
2. **Reliable competitor price** — show a competitor product's min/max price reliably in the saved-URL confirmation, including when the public REST API returns no usable payload, by extracting price from the product-page HTML.
3. **Working multi-provider AI advisor** — make the AI advisor function regardless of API-key format by using whichever provider key is configured (Groq, OpenRouter, or Gemini), with clear localized messages when none is configured.

In addition, this document captures a **preservation/regression contract** so that all currently working capabilities continue to behave exactly as before, and a **public-interface stability contract** so that established function names remain stable for existing call sites.

This is a requirements document only. No source code is changed by this spec.

## Glossary

- **Uzumchi_Bot**: The Telegram bot application rooted at `/projects/sandbox/Uzumchi`, comprising its handlers, services, keyboards, and locales.
- **Main_Menu_Keyboard**: The reply keyboard produced by the public function `main_menu_keyboard(lang)` in `utils/keyboards.py`.
- **Core_Menu_Buttons**: The set of buttons {Products, Orders, Storage, Report, Competitor, AI, Settings}.
- **Removed_Menu_Buttons**: The set of buttons {Weekly, Monthly, Returns}.
- **Analytics_Router**: The aiogram router defined in `handlers/analytics.py`.
- **AI_Handlers**: The handlers registered on the Analytics_Router for the AI advisor flow (`cmd_ai`, `ai_sales_analysis`, `ai_storage_advice`, `ai_question_start`, `ai_question_process`, `ai_back`) and the `AIStates` state group.
- **Competitor_Monitor**: The service module `services/competitor_monitor.py`.
- **Product_Resolver**: The public function `get_product_info_by_url(uzum_url)` in the Competitor_Monitor.
- **Price_Extractor**: The function `get_price_from_html(html)` in the Competitor_Monitor that parses prices from product-page HTML.
- **Competitor_Report**: The text produced by the public function `format_single_product_report(product_name, my_price, info, lang)` in the Competitor_Monitor.
- **Uzum_REST_API**: The public REST endpoint `api.uzum.uz` accessed via `_get_product_from_api`.
- **Product_Page_HTML**: The HTML document of a Uzum product page on `uzum.uz`.
- **Price_Threshold**: The minimum value (greater than 100) below which a parsed numeric value is rejected as a price.
- **AI_Advisor**: The provider-agnostic AI layer in `services/gemini_ai.py`, entered through the public function `ask_gemini(prompt, lang)`.
- **Provider_Selector**: The internal function `_select_providers()` in the AI_Advisor.
- **AI_Provider**: A configured text-completion backend; one of Groq, OpenRouter, or Gemini.
- **Provider_Priority_Order**: The default ordering of AI providers: Groq, then OpenRouter, then Gemini.
- **Prompt_Builders**: The public functions `build_sales_analysis_prompt`, `build_storage_advice_prompt`, and `build_competitor_advice_prompt` in the AI_Advisor.
- **Daily_Report**: The daily report flow driven by `cmd_report_today` in `handlers/main_menu.py`.
- **Product_Fallback_Report**: The report generated from product data when the orders endpoint returns HTTP 403, produced via `build_product_fallback_report` / `product_stats_available`.
- **Scheduler**: The background job service in `services/scheduler.py`, including `run_returns_check`.
- **Health_Endpoints**: The `/ping` and `/health` HTTP endpoints and the self-ping mechanism.
- **lang**: The active interface language, one of {uz, ru}.

## Requirements

### Requirement 1: Remove Weekly, Monthly, and Returns from the main menu

**User Story:** As a seller, I want the Weekly, Monthly, and Returns sections removed from the menu, so that the bot is simpler to use.

#### Acceptance Criteria

1. WHERE lang is uz or ru, THE Main_Menu_Keyboard SHALL render exactly the Core_Menu_Buttons {Products, Orders, Storage, Report, Competitor, AI, Settings}.
2. WHERE lang is uz or ru, THE Main_Menu_Keyboard SHALL exclude every button in the Removed_Menu_Buttons {Weekly, Monthly, Returns}.
3. THE Main_Menu_Keyboard SHALL produce a button-layout configuration whose row sizes sum to 7.
4. THE Uzumchi_Bot SHALL retain the public function name `main_menu_keyboard` with its existing signature `main_menu_keyboard(lang)`.

### Requirement 2: Clean up Weekly, Monthly, and Returns handler code without breaking other features

**User Story:** As a seller, I want the removed sections' handler code cleaned up, so that no dead code remains and no other feature breaks.

#### Acceptance Criteria

1. THE Analytics_Router SHALL exclude handlers for the Weekly section (`cmd_weekly`), the Monthly section (`cmd_monthly`), and the Returns section (`cmd_returns`).
2. THE Analytics_Router SHALL exclude module-level helpers that become unused after the removal of the Weekly, Monthly, and Returns handlers.
3. WHEN `handlers/analytics.py` is imported, THE Analytics_Router SHALL load without raising an ImportError or NameError.
4. THE Analytics_Router SHALL retain the AI_Handlers (`cmd_ai`, `ai_sales_analysis`, `ai_storage_advice`, `ai_question_start`, `ai_question_process`, `ai_back`) and the `AIStates` state group.
5. THE Analytics_Router SHALL retain every import that the retained AI_Handlers reference, including `get_fbs_orders_period`, `get_products`, `get_invoices`, `summarize_orders`, `parse_invoices`, `ask_gemini`, `build_sales_analysis_prompt`, and `build_storage_advice_prompt`.
6. WHEN `main.py` is imported, THE Uzumchi_Bot SHALL register the Analytics_Router with its retained AI_Handlers.

### Requirement 3: Reliable competitor price extraction from HTML

**User Story:** As a seller, when I add a Uzum product URL to competitor monitoring, I want the competitor's price shown reliably in the confirmation, so that I can compare it to my own price.

#### Acceptance Criteria

1. WHEN a valid Uzum product URL is submitted to the Product_Resolver, THE Product_Resolver SHALL return a product information record containing `min_price`, `max_price`, and a `price_source` field.
2. WHEN the Price_Extractor parses Product_Page_HTML that contains at least one numeric value greater than the Price_Threshold, THE Price_Extractor SHALL return a tuple `(min_price, max_price)` where `min_price` equals the smallest qualifying value and `max_price` equals the largest qualifying value.
3. IF the Product_Page_HTML contains no numeric value greater than the Price_Threshold, THEN THE Price_Extractor SHALL return no price result (None).
4. THE Price_Extractor SHALL exclude every numeric value less than or equal to the Price_Threshold from the returned `(min_price, max_price)`.
5. WHEN the Uzum_REST_API returns a payload whose `min_price` is greater than 0, THE Product_Resolver SHALL use the API price and set `price_source` to "api".
6. IF the Uzum_REST_API returns no usable payload or a payload with no positive price AND the Price_Extractor returns a price from the Product_Page_HTML, THEN THE Product_Resolver SHALL populate `min_price` and `max_price` from the HTML price and set `price_source` to "html".
7. IF neither the Uzum_REST_API nor the Price_Extractor yields a price, THEN THE Product_Resolver SHALL set `price_source` to "none" and set `html_only` to true.
8. WHEN the product information record has a `min_price` greater than 0, THE Competitor_Report SHALL include the competitor price block regardless of whether the price source is "api" or "html".
9. IF an error occurs while fetching or parsing the Product_Page_HTML, THEN THE Competitor_Monitor SHALL handle the error internally and return a result without raising to the calling handler.
10. THE Competitor_Monitor SHALL retain the public function names `get_product_info_by_url` and `format_single_product_report` with their existing signatures.

### Requirement 4: Multi-provider AI advisor

**User Story:** As a seller, I want the AI advisor to actually work using whichever AI provider key I configure, so that I receive advice without being blocked by provider-specific setup.

#### Acceptance Criteria

1. THE Provider_Selector SHALL return the configured AI providers ordered by the Provider_Priority_Order (Groq, then OpenRouter, then Gemini), filtered to those whose API key is set.
2. WHERE the `AI_PROVIDER` environment value names an AI provider whose API key is set, THE Provider_Selector SHALL return exactly that single provider.
3. WHEN `ask_gemini` is invoked with at least one configured AI provider, THE AI_Advisor SHALL request a completion from the first provider in the selected order and return its non-empty answer text.
4. IF the first selected AI provider fails or returns an empty response, THEN THE AI_Advisor SHALL attempt the next configured AI provider before returning an error.
5. IF every configured AI provider fails, THEN THE AI_Advisor SHALL return a non-empty localized error message in the active lang.
6. WHEN an AI provider returns a non-200 HTTP response, THE AI_Advisor SHALL log the status code and the response body and SHALL exclude the API key from the log output.
7. THE AI_Advisor SHALL retain the public function name `ask_gemini` with its existing signature `ask_gemini(prompt, lang)`.
8. THE AI_Advisor SHALL retain the Prompt_Builders `build_sales_analysis_prompt`, `build_storage_advice_prompt`, and `build_competitor_advice_prompt` with their existing signatures.

### Requirement 5: API-key format liberty and no-key messaging

**User Story:** As a seller, I want the AI advisor to accept my API key regardless of its format and to tell me clearly when no key is configured, so that I am never blocked by a format check or left without an explanation.

#### Acceptance Criteria

1. THE AI_Advisor SHALL accept any non-empty AI provider API key as usable.
2. THE AI_Advisor SHALL treat a non-empty API key as usable even when the key does not begin with the prefix "AIzaSy".
3. IF no AI provider API key is configured, THEN THE AI_Advisor SHALL return a non-empty localized message in the active lang instructing the seller to add a provider key.
4. IF no AI provider API key is configured, THEN THE AI_Advisor SHALL perform no network call.

### Requirement 6: Preservation of existing capabilities (regression contract)

**User Story:** As a seller, I want all currently working capabilities to keep working unchanged, so that these improvements do not introduce regressions.

#### Acceptance Criteria

1. THE Uzumchi_Bot SHALL preserve the existing behavior of the Products, Orders, and Storage capabilities.
2. THE Uzumchi_Bot SHALL preserve the existing behavior of the Daily_Report, including the Product_Fallback_Report when the orders endpoint returns HTTP 403.
3. THE Uzumchi_Bot SHALL preserve the existing behavior of the finance overlay.
4. THE Uzumchi_Bot SHALL preserve the existing behavior of the competitor monitor list view (`check_saved_urls`).
5. THE Uzumchi_Bot SHALL preserve the existing multi-shop behavior.
6. THE Uzumchi_Bot SHALL preserve the existing charts behavior.
7. THE Scheduler SHALL preserve its existing jobs, including `run_returns_check` and its dependency on `get_returns` from `services/uzum_api.py`.
8. THE Health_Endpoints SHALL preserve the existing behavior of `/ping`, `/health`, and the self-ping mechanism.
9. WHEN `main.py` is imported, THE Uzumchi_Bot SHALL load all routers and the Scheduler without raising an error.

### Requirement 7: Stability of public interfaces

**User Story:** As a developer maintaining the bot, I want the established public function names to remain stable, so that existing call sites continue to work without modification.

#### Acceptance Criteria

1. THE Uzumchi_Bot SHALL retain the public function `ask_gemini` with its existing signature.
2. THE Uzumchi_Bot SHALL retain the public Prompt_Builders `build_sales_analysis_prompt`, `build_storage_advice_prompt`, and `build_competitor_advice_prompt` with their existing signatures.
3. THE Uzumchi_Bot SHALL retain the public function `get_product_info_by_url` with its existing signature.
4. THE Uzumchi_Bot SHALL retain the public function `format_single_product_report` with its existing signature.
5. THE Uzumchi_Bot SHALL retain the public function `main_menu_keyboard` with its existing signature.
