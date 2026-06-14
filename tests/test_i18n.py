"""
i18n totality tests for the new scheduler/report/finance keys.
Every new key must resolve to a non-empty uz + ru string (not the [key] fallback),
and every parameterized key must .format() successfully.
"""
import pytest

from locales.i18n import t, TEXTS

# New keys and the kwargs each one expects when formatted.
NEW_KEYS = {
    "sched_morning_title": {},
    "sched_morning_body": dict(total=1, delivered=1, cancelled=0, revenue=1000),
    "sched_morning_storage": dict(paid=1, alert=0, warn=2, ok=3),
    "sched_storage_header": {},
    "sched_storage_line": dict(icon="🚨", invoice_number="123", days=58, qty=10),
    "sched_delivered": dict(count=2),
    "sched_delivered_detail": dict(name="X", sku="S", price=100, commission=10, profit=70, date="01.01.2024"),
    "sched_rating": dict(shop_name="JoyKid", rating=4.2),
    "sched_forecast_header": {},
    "sched_forecast_line": dict(icon="⚠️", name="Item", days=5),
    "sched_returns": dict(count=3),
    "report_weekly_body": dict(total=5, delivered=4, cancelled=1, revenue=5000),
    "report_weekly_daily_header": {},
    "report_monthly_body": dict(total=50, delivered=40, cancelled=5, revenue=50000),
    "report_monthly_weeks_header": {},
    "finance_commission": dict(commission=1234),
    "finance_logistics": dict(logistics=567),
    "finance_net_profit": dict(profit=8900),
    "finance_margin": dict(margin=42.5),
}


@pytest.mark.parametrize("key", list(NEW_KEYS.keys()))
@pytest.mark.parametrize("lang", ["uz", "ru"])
def test_key_defined_non_empty_both_langs(key, lang):
    assert key in TEXTS, f"missing key {key}"
    assert lang in TEXTS[key], f"missing lang {lang} for {key}"
    value = TEXTS[key][lang]
    assert isinstance(value, str) and value.strip(), (key, lang)


@pytest.mark.parametrize("key,kwargs", list(NEW_KEYS.items()))
@pytest.mark.parametrize("lang", ["uz", "ru"])
def test_key_formats_and_is_not_fallback(key, kwargs, lang):
    rendered = t(key, lang, **kwargs)
    assert rendered, (key, lang)
    assert rendered != f"[{key}]", "key resolved to fallback marker"
    # placeholders must be substituted (no leftover braces for our params)
    assert "{" not in rendered, (key, lang, rendered)


def test_unknown_key_falls_back():
    assert t("___does_not_exist___", "ru") == "[___does_not_exist___]"


def test_existing_t_signature_default_lang_ru():
    # t(key, lang="ru", **kwargs) — calling without lang uses ru.
    assert t("finance_margin", margin=10.0) == TEXTS["finance_margin"]["ru"].format(margin=10.0)
