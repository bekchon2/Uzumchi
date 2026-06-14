"""
Bugfix: robust competitor shop/seller name resolution
(services/competitor_monitor.py).

Property 1: Bug Condition  — Robust shop-name resolution (exploration; FAILS on unfixed)
Property 2: Preservation   — Genuinely-missing names / prices / proxy / manual fallback
Plus unit, orchestrator and integration tests for the two new pure helpers.

Validates: Requirements 1.1, 1.2, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.4
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


URL = "https://uzum.uz/ru/product/test-2855035"


# ─────────────────────────────────────────────────────────────────────────────
# Task 1 — Bug-condition exploration (Property 1). MUST FAIL on unfixed code.
#   These encode the expected behavior and validate the fix once it passes.
# ─────────────────────────────────────────────────────────────────────────────

def test_explore_api_seller_title_resolves():
    # API payload exposes the name under a non-standard field (seller.title).
    # Unfixed: narrow extractor / missing helper -> "—"/error. Fixed: "ACME".
    assert c._extract_shop_name({"seller": {"title": "ACME"}}) == "ACME"


def test_explore_html_seller_object_resolves(monkeypatch):
    # API failed entirely; HTML embeds "seller":{"title":"HtmlShop"}.
    # Unfixed: HTML-primary branch hardcodes "—". Fixed: "HtmlShop".
    html = '<html>{"seller":{"title":"HtmlShop"}}</html>'

    async def _api(_pid):
        return None

    async def _html(_url):
        return html

    monkeypatch.setattr(c, "_get_product_from_api", _api)
    monkeypatch.setattr(c, "_fetch_product_html", _html)
    monkeypatch.setattr(c, "get_price_from_html", lambda h: (130000.0, 150000.0))

    info = _run(c.get_product_info_by_url(URL))
    assert info["shop"] == "HtmlShop"


def test_explore_html_jsonld_brand_resolves(monkeypatch):
    # API failed; HTML JSON-LD brand.name. Unfixed -> "—". Fixed -> "BrandX".
    html = (
        '<script type="application/ld+json">'
        '{"@type":"Product","brand":{"name":"BrandX"}}</script>'
    )

    async def _api(_pid):
        return None

    async def _html(_url):
        return html

    monkeypatch.setattr(c, "_get_product_from_api", _api)
    monkeypatch.setattr(c, "_fetch_product_html", _html)
    monkeypatch.setattr(c, "get_price_from_html", lambda h: (130000.0, 150000.0))

    info = _run(c.get_product_info_by_url(URL))
    assert info["shop"] == "BrandX"



# ─────────────────────────────────────────────────────────────────────────────
# Task 2 — Preservation (Property 2). MUST PASS on unfixed code (baseline) and
#   continue to pass after the fix. Uses only the public orchestrator path.
# ─────────────────────────────────────────────────────────────────────────────

def _patch_resolver(monkeypatch, api_ret, html_ret, price_ret):
    async def _api(_pid):
        return api_ret

    async def _html(_url):
        return html_ret

    monkeypatch.setattr(c, "_get_product_from_api", _api)
    monkeypatch.setattr(c, "_fetch_product_html", _html)
    monkeypatch.setattr(c, "get_price_from_html", lambda h: price_ret)


def test_preserve_missing_shop_stays_dash_html_fallback(monkeypatch):
    # API failed, HTML has a price but NO seller markers -> shop stays "—".
    _patch_resolver(monkeypatch, None, "<html><body>no seller here</body></html>",
                    (130000.0, 150000.0))
    info = _run(c.get_product_info_by_url(URL))
    assert info["shop"] == "—"


def test_preserve_api_shop_present_unchanged(monkeypatch):
    # API already supplies a usable shop name -> kept as-is.
    api = {"title": "T", "min_price": 200000, "max_price": 250000, "price": 225000,
           "shop": "RealShop", "rating": 4.0, "reviews": 10}
    _patch_resolver(monkeypatch, api, "<html>x</html>", (1.0, 2.0))
    info = _run(c.get_product_info_by_url(URL))
    assert info["shop"] == "RealShop"
    assert info["price_source"] == "api"
    assert info["min_price"] == 200000          # price untouched
    assert info["url"] == URL


def test_preserve_price_source_and_html_only_fields(monkeypatch):
    # No price anywhere, no shop markers -> price_source/html_only preserved.
    api = {"title": "OnlyTitle", "min_price": 0, "max_price": 0, "price": 0,
           "shop": "—", "rating": 0, "reviews": 0}
    _patch_resolver(monkeypatch, api, "<html>plain</html>", None)
    info = _run(c.get_product_info_by_url(URL))
    assert info["price_source"] == "none"
    assert info["html_only"] is True
    assert info["shop"] == "—"


if HAS_HYPOTHESIS:
    # Text guaranteed to contain none of the seller/shop markers.
    _safe_text = st.text(alphabet="abcdefghijklmnopqrstuvwxyz 0123456789", max_size=60)

    @settings(max_examples=80)
    @given(_safe_text)
    def test_property_no_markers_preserves_dash(body):
        async def _api(_pid):
            return None

        async def _html(_url):
            return f"<html><body>{body}</body></html>"

        import services.competitor_monitor as cm

        # Patch manually (monkeypatch fixture unavailable inside hypothesis test).
        orig_api = cm._get_product_from_api
        orig_html = cm._fetch_product_html
        orig_price = cm.get_price_from_html
        cm._get_product_from_api = _api
        cm._fetch_product_html = _html
        cm.get_price_from_html = lambda h: (130000.0, 150000.0)
        try:
            info = _run(cm.get_product_info_by_url(URL))
            assert info["shop"] == "—"
        finally:
            cm._get_product_from_api = orig_api
            cm._fetch_product_html = orig_html
            cm.get_price_from_html = orig_price



# ─────────────────────────────────────────────────────────────────────────────
# Task 3.4 — Unit tests for the new pure helpers.
# ─────────────────────────────────────────────────────────────────────────────

def test_extract_seller_title():
    assert c._extract_shop_name({"seller": {"title": "ACME"}}) == "ACME"


def test_extract_seller_name():
    assert c._extract_shop_name({"seller": {"name": "NameShop"}}) == "NameShop"


def test_extract_seller_shopname():
    assert c._extract_shop_name({"seller": {"shopName": "SkuShop"}}) == "SkuShop"


def test_extract_seller_companyname():
    assert c._extract_shop_name({"seller": {"companyName": "CoShop"}}) == "CoShop"


def test_extract_shoptitle_toplevel():
    assert c._extract_shop_name({"shopTitle": "TopShop"}) == "TopShop"


def test_extract_shopname_toplevel():
    assert c._extract_shop_name({"shopName": "TopName"}) == "TopName"


def test_extract_shopinfo_title():
    assert c._extract_shop_name({"shopInfo": {"title": "MegaShop"}}) == "MegaShop"


def test_extract_shopinfo_name():
    assert c._extract_shop_name({"shopInfo": {"name": "InfoName"}}) == "InfoName"


def test_extract_sellername():
    assert c._extract_shop_name({"sellerName": "TopSeller"}) == "TopSeller"


def test_extract_shop_title_name_shopname():
    assert c._extract_shop_name({"shop": {"title": "ShTitle"}}) == "ShTitle"
    assert c._extract_shop_name({"shop": {"name": "ShName"}}) == "ShName"
    assert c._extract_shop_name({"shop": {"shopName": "ShSku"}}) == "ShSku"


def test_extract_toplevel_sellertitle_and_companyname():
    assert c._extract_shop_name({"sellerTitle": "STitle"}) == "STitle"
    assert c._extract_shop_name({"companyName": "Comp"}) == "Comp"


def test_extract_priority_seller_title_wins():
    payload = {
        "seller": {"title": "First", "name": "Second"},
        "shopTitle": "Third",
        "shopInfo": {"title": "Fourth"},
        "shop": {"name": "Fifth"},
        "companyName": "Sixth",
    }
    assert c._extract_shop_name(payload) == "First"


def test_extract_priority_skips_empty_high_priority():
    # seller.* empty -> falls through to shopTitle.
    payload = {"seller": {"title": "   ", "name": ""}, "shopTitle": "Chosen"}
    assert c._extract_shop_name(payload) == "Chosen"


def test_extract_bare_string_seller():
    assert c._extract_shop_name({"seller": "BareSeller"}) == "BareSeller"


def test_extract_bare_string_shop():
    assert c._extract_shop_name({"shop": "BareShop"}) == "BareShop"


def test_extract_nested_non_dict_safe():
    # seller is an int -> not a dict, not a usable name -> falls through.
    assert c._extract_shop_name({"seller": 123, "shopTitle": "Fallback"}) == "Fallback"


def test_extract_missing_returns_empty():
    assert c._extract_shop_name({}) == ""
    assert c._extract_shop_name({"shop": {}}) == ""
    assert c._extract_shop_name({"seller": {}, "shopInfo": {}}) == ""


def test_extract_non_dict_payload():
    assert c._extract_shop_name(None) == ""
    assert c._extract_shop_name("x") == ""


# get_shop_from_html -----------------------------------------------------------

def test_html_sellertitle_key():
    assert c.get_shop_from_html('{"sellerTitle":"KeyShop"}') == "KeyShop"


def test_html_shoptitle_key():
    assert c.get_shop_from_html('{"shopTitle":"ShopKey"}') == "ShopKey"


def test_html_sellername_key():
    assert c.get_shop_from_html('{"sellerName":"NameKey"}') == "NameKey"


def test_html_seller_object_title_then_name():
    assert c.get_shop_from_html('{"seller":{"title":"ObjTitle","name":"ObjName"}}') == "ObjTitle"
    assert c.get_shop_from_html('{"seller":{"name":"OnlyName"}}') == "OnlyName"


def test_html_shopinfo_object():
    assert c.get_shop_from_html('{"shopInfo":{"title":"InfoTitle"}}') == "InfoTitle"


def test_html_jsonld_brand_name():
    html = ('<script type="application/ld+json">'
            '{"@type":"Product","brand":{"name":"BrandX"}}</script>')
    assert c.get_shop_from_html(html) == "BrandX"


def test_html_jsonld_seller_name():
    html = ('<script type="application/ld+json">'
            '{"offers":{"seller":{"name":"SellerLD"}}}</script>')
    # offers.seller is nested; top-level seller object regex also matches "seller":{...}
    assert c.get_shop_from_html(html) == "SellerLD"


def test_html_no_markers_returns_none():
    assert c.get_shop_from_html("<html><body>nothing here</body></html>") is None
    assert c.get_shop_from_html("") is None
    assert c.get_shop_from_html(None) is None


if HAS_HYPOTHESIS:
    _name = st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
                    min_size=1, max_size=20)
    _field = st.sampled_from([
        ("seller", "title"), ("seller", "name"), ("seller", "shopName"),
        ("seller", "companyName"), ("shopTitle",), ("shopName",),
        ("shopInfo", "title"), ("shopInfo", "name"), ("sellerName",),
        ("shop", "title"), ("shop", "name"), ("shop", "shopName"),
        ("sellerTitle",), ("companyName",),
    ])

    @settings(max_examples=120)
    @given(_field, _name)
    def test_property_single_field_resolves_nonempty(field, name):
        if len(field) == 1:
            payload = {field[0]: name}
        else:
            payload = {field[0]: {field[1]: name}}
        result = c._extract_shop_name(payload)
        assert result == name
        assert result != ""

    @settings(max_examples=50)
    @given(st.just(0))
    def test_property_all_empty_resolves_empty(_):
        payload = {
            "seller": {"title": "", "name": "", "shopName": "", "companyName": ""},
            "shopTitle": "", "shopName": "",
            "shopInfo": {"title": "", "name": ""},
            "sellerName": "",
            "shop": {"title": "", "name": "", "shopName": ""},
            "sellerTitle": "", "companyName": "",
        }
        assert c._extract_shop_name(payload) == ""


# ─────────────────────────────────────────────────────────────────────────────
# Task 3.5 — Orchestrator + integration tests.
# ─────────────────────────────────────────────────────────────────────────────

def test_orchestrator_resolves_from_api_payload(monkeypatch):
    api = {"title": "T", "min_price": 200000, "max_price": 250000, "price": 225000,
           "shop": "ApiShop", "rating": 0, "reviews": 0}
    _patch_resolver(monkeypatch, api, "<html>x</html>", (1.0, 2.0))
    info = _run(c.get_product_info_by_url(URL))
    assert info["shop"] == "ApiShop"


def test_orchestrator_resolves_from_html_when_api_shop_empty(monkeypatch):
    api = {"title": "T", "min_price": 200000, "max_price": 250000, "price": 225000,
           "shop": "—", "rating": 0, "reviews": 0}
    html = '<html>{"shopTitle":"HtmlFallbackShop"}</html>'
    _patch_resolver(monkeypatch, api, html, (1.0, 2.0))
    info = _run(c.get_product_info_by_url(URL))
    assert info["shop"] == "HtmlFallbackShop"


def test_orchestrator_resolves_from_html_on_api_failed(monkeypatch):
    html = '<html>{"seller":{"title":"FailoverShop"}}</html>'
    _patch_resolver(monkeypatch, None, html, (130000.0, 150000.0))
    info = _run(c.get_product_info_by_url(URL))
    assert info["shop"] == "FailoverShop"


def test_orchestrator_genuinely_missing_stays_dash(monkeypatch):
    api = {"title": "T", "min_price": 200000, "max_price": 250000, "price": 225000,
           "shop": "—", "rating": 0, "reviews": 0}
    _patch_resolver(monkeypatch, api, "<html>no markers</html>", (1.0, 2.0))
    info = _run(c.get_product_info_by_url(URL))
    assert info["shop"] == "—"


def test_orchestrator_fetches_html_exactly_once(monkeypatch):
    calls = {"n": 0}

    async def _html(_url):
        calls["n"] += 1
        return '<html>{"shopTitle":"OnceShop"}</html>'

    async def _api(_pid):
        return {"title": "T", "min_price": 200000, "max_price": 250000,
                "price": 225000, "shop": "—", "rating": 0, "reviews": 0}

    monkeypatch.setattr(c, "_fetch_product_html", _html)
    monkeypatch.setattr(c, "_get_product_from_api", _api)
    monkeypatch.setattr(c, "get_price_from_html", lambda h: (1.0, 2.0))
    info = _run(c.get_product_info_by_url(URL))
    assert info["shop"] == "OnceShop"
    assert calls["n"] == 1


@pytest.mark.parametrize("lang", ["uz", "ru"])
def test_integration_check_saved_urls_shows_resolved_name(monkeypatch, lang):
    async def _info(_url):
        return {"title": "Prod", "min_price": 100000, "max_price": 100000,
                "price": 100000, "shop": "ResolvedShop", "rating": 0, "reviews": 0,
                "price_source": "api"}

    async def _nosleep(_s):
        return None

    monkeypatch.setattr(c, "get_product_info_by_url", _info)
    monkeypatch.setattr(c.asyncio, "sleep", _nosleep)
    out = _run(c.check_saved_urls(
        "key", [], [{"product_name": "Prod", "uzum_url": URL}], lang))
    assert "🏪 ResolvedShop" in out
    assert "🏪 —" not in out


@pytest.mark.parametrize("lang", ["uz", "ru"])
def test_integration_single_report_shows_shop_when_resolved(lang):
    info = {"title": "Prod", "min_price": 100000, "max_price": 100000,
            "shop": "ResolvedShop", "rating": 0, "reviews": 0, "price_source": "api"}
    out = c.format_single_product_report("Prod", 0, info, lang)
    assert "🏪 ResolvedShop" in out


@pytest.mark.parametrize("lang", ["uz", "ru"])
def test_integration_single_report_omits_shop_when_dash(lang):
    info = {"title": "Prod", "min_price": 100000, "max_price": 100000,
            "shop": "—", "rating": 0, "reviews": 0, "price_source": "api"}
    out = c.format_single_product_report("Prod", 0, info, lang)
    assert "🏪" not in out
