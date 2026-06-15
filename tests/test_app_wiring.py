"""
Final wiring smoke test — Property 3 + Property 12 (Preservation).

Asserts the whole app imports (all routers + scheduler transitively) and that
the analytics router is registered with its AI handlers.

Validates: Requirements 2.6, 6.9
"""


def test_import_main_succeeds():
    import main  # transitively imports start/analytics/main_menu routers + scheduler
    assert main is not None


def test_all_target_modules_import_clean():
    import importlib
    for mod in (
        "handlers.analytics", "services.gemini_ai",
        "services.competitor_monitor", "utils.keyboards",
    ):
        assert importlib.import_module(mod) is not None


def test_analytics_router_has_ai_handlers():
    import handlers.analytics as an
    total = sum(len(obs.handlers) for obs in an.router.observers.values())
    assert total >= 6
    for name in ["cmd_ai", "ai_sales_analysis", "ai_storage_advice",
                 "ai_question_start", "ai_question_process", "ai_back"]:
        assert hasattr(an, name)


def test_public_surface_preserved():
    import services.gemini_ai as g
    import services.competitor_monitor as c
    import utils.keyboards as k
    # Public function names kept stable for existing call sites.
    assert callable(g.ask_gemini)
    assert callable(g.build_sales_analysis_prompt)
    assert callable(g.build_storage_advice_prompt)
    assert callable(g.build_competitor_advice_prompt)
    assert callable(c.get_product_info_by_url)
    assert callable(c.format_single_product_report)
    assert callable(k.main_menu_keyboard)
