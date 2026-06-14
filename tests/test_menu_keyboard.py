"""
Change 1 tests — main menu keyboard exclusivity/layout and analytics router integrity.

Property 1: Keyboard exclusivity
Property 2: Keyboard layout validity
Property 3: Analytics router integrity
Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.3, 2.4, 2.5
"""
import pytest

from utils.keyboards import main_menu_keyboard
from locales.i18n import t

CORE_KEYS = [
    "btn_products", "btn_orders", "btn_storage", "btn_report",
    "btn_competitor", "btn_ai", "btn_settings",
]
REMOVED_KEYS = ["btn_weekly", "btn_monthly", "btn_returns"]


def _button_texts(markup):
    return [btn.text for row in markup.keyboard for btn in row]


@pytest.mark.parametrize("lang", ["uz", "ru"])
def test_main_menu_renders_exactly_core_buttons(lang):
    """Property 1 — exactly the 7 Core_Menu_Buttons appear, in order."""
    markup = main_menu_keyboard(lang)
    texts = _button_texts(markup)
    assert texts == [t(k, lang) for k in CORE_KEYS]


@pytest.mark.parametrize("lang", ["uz", "ru"])
def test_main_menu_excludes_removed_buttons(lang):
    """Property 1 — none of weekly/monthly/returns labels appear."""
    texts = set(_button_texts(main_menu_keyboard(lang)))
    for key in REMOVED_KEYS:
        assert t(key, lang) not in texts


@pytest.mark.parametrize("lang", ["uz", "ru"])
def test_main_menu_renders_seven_buttons(lang):
    """Property 2 — layout rows sum to 7 buttons."""
    markup = main_menu_keyboard(lang)
    total = sum(len(row) for row in markup.keyboard)
    assert total == 7


def test_analytics_imports_clean_and_ai_handlers_present():
    """Property 3 — import is clean and AI handlers are present, removed ones absent."""
    import importlib
    import handlers.analytics as an
    importlib.reload(an)

    # Router object exists
    assert an.router is not None

    # AI handlers retained
    for name in [
        "cmd_ai", "ai_sales_analysis", "ai_storage_advice",
        "ai_question_start", "ai_question_process", "ai_back",
    ]:
        assert hasattr(an, name), f"missing AI handler {name}"
    assert hasattr(an, "AIStates")

    # Removed handlers absent
    for name in ["cmd_weekly", "cmd_monthly", "cmd_returns",
                 "_build_daily_data", "_is_in_week"]:
        assert not hasattr(an, name), f"removed symbol still present: {name}"


def test_analytics_router_registered_handlers_nonempty():
    """Property 3 — the router actually has handlers registered."""
    import handlers.analytics as an
    # message + callback handlers across observers
    total = sum(len(obs.handlers) for obs in an.router.observers.values())
    assert total >= 6
