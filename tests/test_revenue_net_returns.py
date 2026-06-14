"""
Bugfix: net-of-returns revenue estimate
(services/uzum_api.py::get_sales_stats_from_products).

Property 3: Bug Condition  — Net-of-returns revenue (exploration; FAILS on unfixed)
Property 4: Preservation   — Counts, keys, labels, zero-return revenue
Plus unit + property-based + integration tests.

Validates: Requirements 1.5, 1.6, 2.5, 2.6, 2.7, 3.3, 3.4
"""
import asyncio

import pytest

import services.uzum_api as u

try:
    from hypothesis import given, settings, strategies as st
    HAS_HYPOTHESIS = True
except Exception:  # pragma: no cover
    HAS_HYPOTHESIS = False


def _run(coro):
    return asyncio.run(coro)


def _patch_products(monkeypatch, products):
    async def _get_products(_api_key, _shop_id):
        return products

    monkeypatch.setattr(u, "get_products", _get_products)


def _gross(products):
    return sum(
        int(s.get("quantitySold") or 0) * float(s.get("price") or s.get("purchasePrice") or 0)
        for p in products for s in p.get("skuList", [])
    )


def _net(products):
    return sum(
        max(0, int(s.get("quantitySold") or 0) - int(s.get("quantityReturned") or 0))
        * float(s.get("price") or s.get("purchasePrice") or 0)
        for p in products for s in p.get("skuList", [])
    )


EXPECTED_KEYS = {
    "total_sold", "total_returned", "total_revenue",
    "low_stock_count", "out_count", "products_count",
}


# ─────────────────────────────────────────────────────────────────────────────
# Task 4 — Bug-condition exploration (Property 3). MUST FAIL on unfixed code.
# ─────────────────────────────────────────────────────────────────────────────

def test_explore_revenue_nets_returns(monkeypatch):
    # One SKU: sold=100, returned=10, price=21000.
    # Unfixed: 100*21000 = 2_100_000. Fixed: 90*21000 = 1_890_000.
    products = [{"skuList": [
        {"quantitySold": 100, "quantityReturned": 10, "price": 21000, "quantityActive": 50},
    ]}]
    _patch_products(monkeypatch, products)
    stats = _run(u.get_sales_stats_from_products("key", 1))
    assert stats["total_revenue"] == 1_890_000



# ─────────────────────────────────────────────────────────────────────────────
# Task 5 — Preservation (Property 4). MUST PASS on unfixed code and after fix.
# ─────────────────────────────────────────────────────────────────────────────

def test_preserve_zero_return_revenue_equals_gross(monkeypatch):
    products = [{"skuList": [
        {"quantitySold": 50, "quantityReturned": 0, "price": 2000, "quantityActive": 10},
        {"quantitySold": 30, "quantityReturned": 0, "price": 5000, "quantityActive": 3},
    ]}]
    _patch_products(monkeypatch, products)
    stats = _run(u.get_sales_stats_from_products("key", 1))
    assert stats["total_revenue"] == _gross(products)
    assert stats["total_revenue"] == 50 * 2000 + 30 * 5000


def test_preserve_counts_and_keys(monkeypatch):
    products = [{"skuList": [
        {"quantitySold": 10, "quantityReturned": 3, "price": 1000, "quantityActive": 0},
        {"quantitySold": 5, "quantityReturned": 1, "price": 2000, "quantityActive": 4},
        {"quantitySold": 0, "quantityReturned": 0, "price": 3000, "quantityActive": 100},
    ]}]
    _patch_products(monkeypatch, products)
    stats = _run(u.get_sales_stats_from_products("key", 1))
    assert set(stats.keys()) == EXPECTED_KEYS
    assert stats["total_sold"] == 15            # raw sum: 10 + 5 + 0
    assert stats["total_returned"] == 4         # raw sum: 3 + 1 + 0
    assert stats["out_count"] == 1              # one SKU with quantityActive == 0
    assert stats["low_stock_count"] == 1        # one SKU with quantityActive == 4 (<=5)
    assert stats["products_count"] == 1


if HAS_HYPOTHESIS:
    _sku_zero_returns = st.fixed_dictionaries({
        "quantitySold": st.integers(min_value=0, max_value=1000),
        "quantityReturned": st.just(0),
        "price": st.integers(min_value=0, max_value=500000),
        "quantityActive": st.integers(min_value=0, max_value=1000),
    })

    @settings(max_examples=120)
    @given(st.lists(st.lists(_sku_zero_returns, max_size=5), max_size=5))
    def test_property_zero_returns_preserves_gross(product_skus):
        products = [{"skuList": skus} for skus in product_skus]

        async def _get_products(_a, _s):
            return products

        orig = u.get_products
        u.get_products = _get_products
        try:
            stats = _run(u.get_sales_stats_from_products("key", 1))
        finally:
            u.get_products = orig
        assert stats["total_revenue"] == _gross(products)
        assert set(stats.keys()) == EXPECTED_KEYS
        assert stats["total_returned"] == 0



# ─────────────────────────────────────────────────────────────────────────────
# Task 6.4 — Unit + property-based + integration tests for the fixed behavior.
# ─────────────────────────────────────────────────────────────────────────────

def test_unit_with_returns_nets_and_le_gross(monkeypatch):
    products = [{"skuList": [
        {"quantitySold": 100, "quantityReturned": 10, "price": 21000, "quantityActive": 5},
        {"quantitySold": 40, "quantityReturned": 5, "price": 10000, "quantityActive": 2},
    ]}]
    _patch_products(monkeypatch, products)
    stats = _run(u.get_sales_stats_from_products("key", 1))
    assert stats["total_revenue"] == _net(products)
    assert stats["total_revenue"] <= _gross(products)
    assert stats["total_revenue"] == 90 * 21000 + 35 * 10000


def test_unit_returned_gt_sold_contributes_zero(monkeypatch):
    products = [{"skuList": [
        {"quantitySold": 5, "quantityReturned": 8, "price": 1000, "quantityActive": 1},
        {"quantitySold": 20, "quantityReturned": 2, "price": 3000, "quantityActive": 7},
    ]}]
    _patch_products(monkeypatch, products)
    stats = _run(u.get_sales_stats_from_products("key", 1))
    # First SKU: max(0, 5-8)=0 contribution. Second: 18*3000.
    assert stats["total_revenue"] == 18 * 3000
    assert stats["total_revenue"] >= 0
    # Raw counts unchanged.
    assert stats["total_sold"] == 25
    assert stats["total_returned"] == 10


def test_unit_real_world_example_moves_toward_real(monkeypatch):
    # From the bug report: gross overcounts; net is lower (still approximate).
    products = [{"skuList": [
        {"quantitySold": 100, "quantityReturned": 10, "price": 21000, "quantityActive": 5},
    ]}]
    _patch_products(monkeypatch, products)
    stats = _run(u.get_sales_stats_from_products("key", 1))
    assert stats["total_revenue"] == 1_890_000
    assert stats["total_revenue"] < _gross(products)  # 2_100_000


if HAS_HYPOTHESIS:
    _sku = st.fixed_dictionaries({
        "quantitySold": st.integers(min_value=0, max_value=1000),
        "quantityReturned": st.integers(min_value=0, max_value=1000),
        "price": st.integers(min_value=0, max_value=500000),
        "quantityActive": st.integers(min_value=0, max_value=1000),
    })

    @settings(max_examples=200)
    @given(st.lists(st.lists(_sku, max_size=5), max_size=5))
    def test_property_revenue_net_invariants(product_skus):
        products = [{"skuList": skus} for skus in product_skus]

        async def _get_products(_a, _s):
            return products

        orig = u.get_products
        u.get_products = _get_products
        try:
            stats = _run(u.get_sales_stats_from_products("key", 1))
        finally:
            u.get_products = orig
        assert stats["total_revenue"] == _net(products)
        assert stats["total_revenue"] >= 0
        assert stats["total_revenue"] <= _gross(products)
        assert stats["total_sold"] == sum(
            int(s["quantitySold"]) for p in products for s in p["skuList"])
        assert stats["total_returned"] == sum(
            int(s["quantityReturned"]) for p in products for s in p["skuList"])
        assert set(stats.keys()) == EXPECTED_KEYS


def test_integration_docstring_still_approximate():
    # The function stays labelled approximate ("taxminiy") and adds no finance call.
    assert "taxminiy" in (u.get_sales_stats_from_products.__doc__ or "").lower()
