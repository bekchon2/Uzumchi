"""
Unit + lightweight property tests for the additive finance functions in
services/uzum_api.py: extract_finance_orders, parse_finance_order, summarize_finance_orders.
"""
import random

from services.uzum_api import (
    extract_finance_orders,
    parse_finance_order,
    summarize_finance_orders,
)


# ─── extract_finance_orders ───────────────────────────────────────────────────

def test_extract_from_each_container_key():
    for key in ("orderItems", "orders", "items", "content"):
        assert extract_finance_orders({key: [{"sellPrice": 1}]}) == [{"sellPrice": 1}]


def test_extract_from_bare_list():
    assert extract_finance_orders([{"sellPrice": 9}]) == [{"sellPrice": 9}]


def test_extract_handles_empty_and_non_dict():
    assert extract_finance_orders({}) == []
    assert extract_finance_orders(None) == []
    assert extract_finance_orders(123) == []


# ─── parse_finance_order ──────────────────────────────────────────────────────

def test_parse_defaults_for_missing_numerics():
    p = parse_finance_order({})
    assert p["sell_price"] == 0
    assert p["commission"] == 0
    assert p["seller_profit"] == 0
    assert p["logistics"] == 0
    assert p["amount"] == 1  # amount defaults to 1
    assert p["date"] == 0
    assert p["date_issued"] == 0
    assert p["sku_title"] == ""
    assert p["product_title"] == ""


def test_parse_maps_all_fields():
    raw = {
        "id": 7, "orderId": 42, "status": "DELIVERED",
        "date": 1700000000000, "dateIssued": 1700100000000,
        "sellPrice": 1000, "commission": 120, "sellerProfit": 800,
        "logisticDeliveryFee": 80, "amount": 3,
        "skuTitle": "Red / L", "productTitle": "T-Shirt",
    }
    p = parse_finance_order(raw)
    assert p["id"] == "7" and p["order_id"] == "42"
    assert p["status"] == "DELIVERED"
    assert p["date"] == 1700000000000 and p["date_issued"] == 1700100000000
    assert p["sell_price"] == 1000 and p["commission"] == 120
    assert p["seller_profit"] == 800 and p["logistics"] == 80
    assert p["amount"] == 3
    assert p["sku_title"] == "Red / L" and p["product_title"] == "T-Shirt"


def test_parse_sellprice_falls_back_to_sellerprice():
    assert parse_finance_order({"sellerPrice": 555})["sell_price"] == 555


# ─── summarize_finance_orders ─────────────────────────────────────────────────

def test_summarize_basic_aggregation():
    raw = {"orderItems": [
        {"sellPrice": 1000, "commission": 100, "sellerProfit": 700, "logisticDeliveryFee": 50},
        {"sellPrice": 500, "commission": 50, "sellerProfit": 350, "logisticDeliveryFee": 25},
    ]}
    s = summarize_finance_orders(raw)
    assert s["count"] == 2
    assert s["revenue"] == 1500
    assert s["commission"] == 150
    assert s["logistics"] == 75
    assert s["net_profit"] == 1050
    assert abs(s["margin_pct"] - (1050 / 1500 * 100)) < 1e-9


def test_summarize_revenue_zero_margin_is_zero():
    # empty
    assert summarize_finance_orders({"orderItems": []})["margin_pct"] == 0
    # revenue == 0 but profit present -> still 0 (no ZeroDivision)
    s = summarize_finance_orders({"orderItems": [{"sellPrice": 0, "sellerProfit": 5}]})
    assert s["revenue"] == 0
    assert s["margin_pct"] == 0


# ─── Property-style tests (deterministic random sampling, no hypothesis dep) ───

def test_property_aggregation_equals_sum():
    rng = random.Random(1234)
    for _ in range(200):
        n = rng.randint(0, 20)
        items = [{
            "sellPrice": rng.randint(0, 100000),
            "commission": rng.randint(0, 20000),
            "sellerProfit": rng.randint(0, 80000),
            "logisticDeliveryFee": rng.randint(0, 5000),
        } for _ in range(n)]
        s = summarize_finance_orders({"orderItems": items})
        assert s["revenue"] == sum(i["sellPrice"] for i in items)
        assert s["commission"] == sum(i["commission"] for i in items)
        assert s["logistics"] == sum(i["logisticDeliveryFee"] for i in items)
        assert s["net_profit"] == sum(i["sellerProfit"] for i in items)


def test_property_margin_bounds():
    rng = random.Random(99)
    for _ in range(200):
        n = rng.randint(1, 15)
        items = []
        for _ in range(n):
            sell = rng.randint(1, 100000)
            profit = rng.randint(0, sell)  # seller_profit in [0, sell_price]
            items.append({"sellPrice": sell, "sellerProfit": profit})
        s = summarize_finance_orders({"orderItems": items})
        if s["revenue"] > 0:
            assert 0 <= s["margin_pct"] <= 100
        else:
            assert s["margin_pct"] == 0
