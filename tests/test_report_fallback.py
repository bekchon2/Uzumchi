"""
Unit + property tests for the product-based 403 fallback builder/predicate and
its i18n keys (report_fallback_summary / report_fallback_note).

Covers tasks 4.1 (builder), 4.2 (predicate), 4.3 (i18n keys), 4.4 (PBT builder).
"""
import pytest

from locales.i18n import t, TEXTS
from handlers.report_fallback import (
    build_product_fallback_report, product_stats_available
)

# Mirrors the exact return shape of get_sales_stats_from_products.
SAMPLE = dict(
    total_sold=120,
    total_returned=5,
    total_revenue=4500000.0,
    low_stock_count=2,
    out_count=1,
    products_count=8,
)


# ─── 4.1 Builder ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("lang", ["uz", "ru"])
def test_builder_includes_all_six_figures_and_note(lang):
    text = build_product_fallback_report(SAMPLE, lang)
    # Each figure is rendered.
    assert "120" in text                 # total_sold
    assert "4,500,000" in text           # total_revenue with thousands separators
    assert "8" in text                   # products_count
    # The summary body and the note are both present.
    assert t("report_fallback_summary", lang, **SAMPLE) in text
    assert t("report_fallback_note", lang) in text
    # No unsubstituted placeholders survive.
    assert "{" not in text and "}" not in text


@pytest.mark.parametrize("lang", ["uz", "ru"])
def test_builder_low_and_out_counts_present(lang):
    stats = dict(SAMPLE, low_stock_count=7, out_count=3, total_revenue=0.0)
    text = build_product_fallback_report(stats, lang)
    assert "7" in text   # low_stock_count
    assert "3" in text   # out_count


def test_builder_revenue_uses_thousands_separator():
    text = build_product_fallback_report(SAMPLE, "ru")
    assert "4,500,000" in text
    assert "4500000" not in text.replace("4,500,000", "")


# ─── 4.2 Predicate ───────────────────────────────────────────────────────────

def test_predicate_true_when_products_present():
    assert product_stats_available({"products_count": 5, "total_sold": 1}) is True


def test_predicate_false_for_empty_dict():
    assert product_stats_available({}) is False


def test_predicate_false_for_zero_products():
    assert product_stats_available({"products_count": 0}) is False


# ─── 4.3 i18n key presence / totality ────────────────────────────────────────

NEW_KEYS = ["report_fallback_summary", "report_fallback_note"]


@pytest.mark.parametrize("key", NEW_KEYS)
@pytest.mark.parametrize("lang", ["uz", "ru"])
def test_new_keys_defined_non_empty(key, lang):
    assert key in TEXTS, f"missing key {key}"
    assert lang in TEXTS[key], f"missing lang {lang} for {key}"
    assert isinstance(TEXTS[key][lang], str) and TEXTS[key][lang].strip()


@pytest.mark.parametrize("lang", ["uz", "ru"])
def test_summary_formats_without_fallback_or_leftover_braces(lang):
    rendered = t("report_fallback_summary", lang, **SAMPLE)
    assert rendered != "[report_fallback_summary]"
    assert "{" not in rendered and "}" not in rendered


@pytest.mark.parametrize("lang", ["uz", "ru"])
def test_note_is_not_fallback_marker(lang):
    rendered = t("report_fallback_note", lang)
    assert rendered != "[report_fallback_note]"
    assert rendered.strip()


# ─── 4.4 Property-based: builder never raises, always includes the note ──────

try:
    from hypothesis import given, settings, strategies as st
    _HAS_HYPOTHESIS = True
except ImportError:  # pragma: no cover - PBT optional
    _HAS_HYPOTHESIS = False


@pytest.mark.skipif(not _HAS_HYPOTHESIS, reason="hypothesis not installed")
def test_builder_property_never_raises_and_includes_all():
    @settings(max_examples=200)
    @given(
        total_sold=st.integers(min_value=0, max_value=10**7),
        total_returned=st.integers(min_value=0, max_value=10**6),
        total_revenue=st.floats(
            min_value=0, max_value=10**12,
            allow_nan=False, allow_infinity=False,
        ),
        low_stock_count=st.integers(min_value=0, max_value=10**4),
        out_count=st.integers(min_value=0, max_value=10**4),
        products_count=st.integers(min_value=1, max_value=10**4),
    )
    def _prop(total_sold, total_returned, total_revenue,
              low_stock_count, out_count, products_count):
        stats = dict(
            total_sold=total_sold, total_returned=total_returned,
            total_revenue=total_revenue, low_stock_count=low_stock_count,
            out_count=out_count, products_count=products_count,
        )
        for lang in ("uz", "ru"):
            text = build_product_fallback_report(stats, lang)
            # never raises, always appends the localized note,
            # and never leaves unsubstituted placeholders.
            assert t("report_fallback_note", lang) in text
            assert "{" not in text and "}" not in text

    _prop()
