"""
Integration-style tests driving `cmd_orders` with the Uzum API functions mocked.

Fix B note: the daily Report handler (`cmd_report_today`) has been removed, so the
three daily-report cases that previously lived here were deleted. The orders-present
and 403-fallback *preservation* intent is retargeted onto `cmd_orders`, which carries
its own INLINE product-based 403 fallback (it does NOT call `report_fallback`):

- Orders present                              -> full order report + finance overlay
- All-403 orders ([]) + product stats present -> inline product-stats fallback text
- All-403 orders ([]) + empty stats ({})       -> existing zeroed order report

Covers tasks 5 (preservation) and 6.4 (verify) for Fix B.
"""
import asyncio

import handlers.main_menu as mm


# ─── Test doubles ────────────────────────────────────────────────────────────

def _aret(value):
    """Build an async function that ignores args and returns `value`."""
    async def _inner(*args, **kwargs):
        return value
    return _inner


class _SentMessage:
    """The message the bot 'sends'; captures the final rendered text."""
    def __init__(self, store):
        self._store = store

    async def edit_text(self, text, **kwargs):
        self._store["rendered"] = text

    async def answer(self, text, **kwargs):
        self._store["rendered"] = text


class _FakeUser:
    def __init__(self, uid=1):
        self.id = uid
        self.username = "tester"


class FakeMessage:
    """Incoming message; .answer() returns the capturing _SentMessage."""
    def __init__(self, store, uid=1):
        self.from_user = _FakeUser(uid)
        self._store = store

    async def answer(self, text, **kwargs):
        self._store.setdefault("loading", []).append(text)
        return _SentMessage(self._store)


def _run(coro):
    return asyncio.run(coro)


# ─── Fixtures / sample data ──────────────────────────────────────────────────

USER = {"api_key": "key", "shop_id": 123, "lang": "uz", "shop_name": "JoyKid"}

PRODUCTS = [
    {"title": "Mahsulot A", "skuList": [{"quantityActive": 3, "price": 50000}]},
    {"title": "Mahsulot B", "skuList": [{"quantityActive": 0, "price": 70000}]},
]

STATS = {
    "total_sold": 120,
    "total_returned": 5,
    "total_revenue": 4500000.0,
    "low_stock_count": 2,
    "out_count": 1,
    "products_count": 8,
}

ORDERS = [{"status": "DELIVERED", "finalPrice": 100000, "id": 1, "createdAt": 0}]

FINANCE = {
    "orders": [
        {
            "sellPrice": 100000,
            "commission": 10000,
            "sellerProfit": 70000,
            "logisticDeliveryFee": 5000,
        }
    ]
}


# ─── cmd_orders preservation ─────────────────────────────────────────────────

def test_orders_present_full_report_with_finance(monkeypatch):
    """Orders present -> full order summary + finance overlay (unchanged)."""
    monkeypatch.setattr(mm, "get_user", _aret(USER))
    monkeypatch.setattr(mm, "get_fbs_orders", _aret(ORDERS))
    monkeypatch.setattr(mm, "get_products", _aret(PRODUCTS))
    monkeypatch.setattr(mm, "get_sales_stats_from_products", _aret(STATS))
    monkeypatch.setattr(mm, "get_finance_orders", _aret(FINANCE))

    store = {}
    _run(mm.cmd_orders(FakeMessage(store)))
    text = store["rendered"]

    assert "Jami: <b>1</b>" in text          # order-based summary
    assert "Komissiya" in text               # finance overlay present


def test_orders_403_inline_product_fallback(monkeypatch):
    """All-403 orders ([]) but product stats available -> inline product fallback."""
    monkeypatch.setattr(mm, "get_user", _aret(USER))
    monkeypatch.setattr(mm, "get_fbs_orders", _aret([]))
    monkeypatch.setattr(mm, "get_products", _aret(PRODUCTS))
    monkeypatch.setattr(mm, "get_sales_stats_from_products", _aret(STATS))
    monkeypatch.setattr(mm, "get_finance_orders", _aret({}))

    store = {}
    _run(mm.cmd_orders(FakeMessage(store)))
    text = store["rendered"]

    assert "120" in text                     # approximate sold qty from products
    assert "API ruxsati yo'q" in text        # inline permission note (uz)


def test_orders_403_empty_stats_zeroed_report(monkeypatch):
    """All-403 orders ([]) and empty stats ({}) -> existing zeroed order report."""
    monkeypatch.setattr(mm, "get_user", _aret(USER))
    monkeypatch.setattr(mm, "get_fbs_orders", _aret([]))
    monkeypatch.setattr(mm, "get_products", _aret(PRODUCTS))
    monkeypatch.setattr(mm, "get_sales_stats_from_products", _aret({}))
    monkeypatch.setattr(mm, "get_finance_orders", _aret({}))

    store = {}
    _run(mm.cmd_orders(FakeMessage(store)))
    text = store["rendered"]

    assert "Jami: <b>0</b>" in text          # zeroed order summary preserved
    assert "API ruxsati yo'q" not in text    # inline fallback NOT triggered
