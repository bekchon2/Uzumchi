"""
i18n totality + format-safety for the new daily-report and sale-push keys.

Feature: products-daily-sale-notifications
Property 8 (localization totality)
"""
import pytest

from locales.i18n import t, TEXTS

NEW_KEYS = {
    "product_report_title": {},
    "product_report_body": dict(total_active=12, total_stock=340, low_count=3, out_count=1),
    "product_report_item": dict(name="Cup", qty=4),
    "sale_push_title": {},
    "sale_push_item": dict(product="Cup", variant="Red", sold=2, remaining=5),
}


@pytest.mark.parametrize("key", list(NEW_KEYS.keys()))
@pytest.mark.parametrize("lang", ["uz", "ru"])
def test_new_key_defined_non_empty_both_langs(key, lang):
    assert key in TEXTS, f"missing key {key}"
    assert lang in TEXTS[key], f"missing lang {lang} for {key}"
    value = TEXTS[key][lang]
    assert isinstance(value, str) and value.strip(), (key, lang)


@pytest.mark.parametrize("key,kwargs", list(NEW_KEYS.items()))
@pytest.mark.parametrize("lang", ["uz", "ru"])
def test_new_key_formats_with_no_unresolved_placeholders(key, kwargs, lang):
    rendered = t(key, lang, **kwargs)
    assert rendered, (key, lang)
    assert rendered != f"[{key}]", "key resolved to fallback marker"
    assert "{" not in rendered, (key, lang, rendered)


def test_body_param_values_present():
    out = t("product_report_body", "ru", total_active=12, total_stock=340, low_count=3, out_count=1)
    for v in ("12", "340", "3", "1"):
        assert v in out


def test_sale_item_param_values_present():
    out = t("sale_push_item", "uz", product="Cup", variant="Red", sold=2, remaining=5)
    for v in ("Cup", "Red", "2", "5"):
        assert v in out
