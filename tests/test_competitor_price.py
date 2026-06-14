"""
Change 2 tests — competitor HTML price extraction and resolver price-source.

Property 4: Price extraction soundness
Property 5: Price threshold
Property 6: API-preserves-when-present
Property 7: Report shows price when available
Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 7.4
"""
import asyncio

import pytest

import services.competitor_monitor as c

try:
    from hypothesis import given, settings, strategies as st
    HAS_HYPOTHESIS = True
except Exception:  # pragma: no cover
    HAS_HYPOTHESIS = False


def _run(coro):
    return asyncio.run(coro)


# ─── Example-based price extraction (Property 4, 5) ──────────────────────────

def test_jsonld_offers_price():
    html = '<script type="application/ld+json">{"@type":"Product","offers":{"price":"249000"}}</script>'
    assert c.get_price_from_html(html) == (249000.0, 249000.0)


def test_jsonld_low_high_price():
    html = (
        '<script type="application/ld+json">'
        '{"offers":{"lowPrice":"100000","highPrice":"300000"}}</script>'
    )
    assert c.get_price_from_html(html) == (100000.0, 300000.0)


def test_embedded_sellprice_keys():
    html = '{"sellPrice":150000,"purchasePrice":120000,"minSellPrice":140000}'
    lo, hi = c.get_price_from_html(html)
    assert lo == 120000.0 and hi == 150000.0


def test_threshold_rejects_small_values():
    # 50 and 99 are <= 100 (threshold), only 12345 qualifies.
    html = '{"price":50,"sellPrice":99,"fullPrice":12345}'
    assert c.get_price_from_html(html) == (12345.0, 12345.0)


def test_no_price_returns_none():
    assert c.get_price_from_html("<html><body>no prices here</body></html>") is None
    assert c.get_price_from_html("") is None


def test_accumulate_price_threshold():
    prices = []
    c._accumulate_price(100, prices)      # not > 100
    c._accumulate_price(100.5, prices)    # > 100
    c._accumulate_price("abc", prices)    # invalid
    c._accumulate_price(None, prices)
    assert prices == [100.5]


# ─── Property-based (Property 4, 5) ──────────────────────────────────────────

if HAS_HYPOTHESIS:
    @settings(max_examples=100)
    @given(st.lists(st.integers(min_value=101, max_value=10_000_000), min_size=1, max_size=8))
    def test_property_min_max_over_qualifying(values):
        # Build embedded-JSON HTML from the values.
        html = "".join(f'"sellPrice":{v},' for v in values)
        result = c.get_price_from_html(html)
        assert result == (float(min(values)), float(max(values)))

    @settings(max_examples=100)
    @given(st.lists(st.integers(min_value=0, max_value=100), min_size=1, max_size=8))
    def test_property_small_values_never_appear(values):
        html = "".join(f'"sellPrice":{v},' for v in values)
        assert c.get_price_from_html(html) is None


# ─── Resolver price-source selection (Property 6) ────────────────────────────

def _patch(monkeypatch, api_ret, html_ret, price_ret):
    async def _api(_pid):
        return api_ret

    async def _html(_url):
        return html_ret

    monkeypatch.setattr(c, "_get_product_from_api", _api)
    monkeypatch.setattr(c, "_fetch_product_html", _html)
    monkeypatch.setattr(c, "get_price_from_html", lambda h: price_ret)


URL = "https://uzum.uz/ru/product/test-2855035"


def test_resolver_api_with_price_keeps_api(monkeypatch):
    api = {"title": "T", "min_price": 200000, "max_price": 250000, "price": 225000,
           "shop": "S", "rating": 4.0, "reviews": 10}
    _patch(monkeypatch, api, "<html>x</html>", (1.0, 2.0))  # html price would be junk
    info = _run(c.get_product_info_by_url(URL))
    assert info["price_source"] == "api"
    assert info["min_price"] == 200000          # API price NOT overwritten
    assert info["url"] == URL


def test_resolver_api_null_uses_html(monkeypatch):
    _patch(monkeypatch, None, "<html>x</html>", (130000.0, 180000.0))
    info = _run(c.get_product_info_by_url(URL))
    assert info["price_source"] == "html"
    assert info["min_price"] == 130000.0 and info["max_price"] == 180000.0
    assert info["html_only"] is False


def test_resolver_api_zero_price_falls_back_to_html(monkeypatch):
    api = {"title": "T", "min_price": 0, "max_price": 0, "price": 0,
           "shop": "—", "rating": 0, "reviews": 0}
    _patch(monkeypatch, api, "<html>x</html>", (140000.0, 140000.0))
    info = _run(c.get_product_info_by_url(URL))
    assert info["price_source"] == "html"
    assert info["min_price"] == 140000.0
    assert info["html_only"] is False


def test_resolver_no_price_anywhere(monkeypatch):
    # API has title but no price, HTML has no price.
    api = {"title": "OnlyTitle", "min_price": 0, "max_price": 0, "price": 0,
           "shop": "—", "rating": 0, "reviews": 0}
    _patch(monkeypatch, api, "<html>x</html>", None)
    info = _run(c.get_product_info_by_url(URL))
    assert info["price_source"] == "none"
    assert info["html_only"] is True


def test_resolver_no_api_html_title_only(monkeypatch):
    async def _api(_pid):
        return None

    async def _html(_url):
        return "<html><title>Some Product Name</title></html>"

    monkeypatch.setattr(c, "_get_product_from_api", _api)
    monkeypatch.setattr(c, "_fetch_product_html", _html)
    monkeypatch.setattr(c, "get_price_from_html", lambda h: None)
    info = _run(c.get_product_info_by_url(URL))
    assert info["price_source"] == "none"
    assert info["html_only"] is True
    assert info["title"]


def test_resolver_invalid_url_returns_none(monkeypatch):
    assert _run(c.get_product_info_by_url("not-a-url")) is None


def test_resolver_handles_fetch_error_internally(monkeypatch):
    # _fetch_product_html returns None (as it does on error); API also None.
    async def _api(_pid):
        return None

    async def _html(_url):
        return None

    monkeypatch.setattr(c, "_get_product_from_api", _api)
    monkeypatch.setattr(c, "_fetch_product_html", _html)
    # No exception should propagate.
    info = _run(c.get_product_info_by_url(URL))
    assert info is None


# ─── Report rendering (Property 7) ───────────────────────────────────────────

def test_report_shows_price_block_api_source():
    info = {"title": "T", "min_price": 200000, "max_price": 250000,
            "shop": "S", "rating": 0, "reviews": 0, "price_source": "api"}
    out_ru = c.format_single_product_report("Mahsulot", 210000, info, "ru")
    out_uz = c.format_single_product_report("Mahsulot", 210000, info, "uz")
    assert "Цены" in out_ru and "200,000" in out_ru
    assert "Narxlar" in out_uz


def test_report_shows_price_block_html_source():
    info = {"title": "T", "min_price": 130000, "max_price": 130000,
            "shop": "—", "rating": 0, "reviews": 0, "price_source": "html",
            "html_only": False}
    out = c.format_single_product_report("Mahsulot", 0, info, "ru")
    assert "Цены" in out and "130,000" in out
