"""
Integration-style tests driving the three report handlers with the Uzum API
functions mocked, covering both the 403 fallback path and the orders-present
preservation path.

- All-403 orders ([]) + products available  -> fallback summary + note
- Orders present                            -> full report + finance overlay, no note
- Non-403 product failure ({} stats)        -> no fallback, existing zeroed report

Covers tasks 1 (exploration), 2.1/2.2 (preservation), 3.6/3.7 (verify), 4.5.
"""
import asyncio

import handlers.main_menu as mm
from locales.i18n import t


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

NOTE_UZ = t("report_fallback_note", "uz")
SUMMARY_HEADER_UZ = "Mahsulot asosidagi taxminiy hisobot"


# ─── Daily report (cmd_report_today) ─────────────────────────────────────────

def test_daily_fallback_on_403_orders(monkeypatch):
    monkeypatch.setattr(mm, "get_user", _aret(USER))
    monkeypatch.setattr(mm, "get_fbs_orders", _aret([]))           # all-403 -> []
    monkeypatch.setattr(mm, "get_products", _aret(PRODUCTS))
    monkeypatch.setattr(mm, "get_sales_stats_from_products", _aret(STATS))
    monkeypatch.setattr(mm, "get_finance_orders", _aret({}))

    store = {}
    _run(mm.cmd_report_today(FakeMessage(store)))
    text = store["rendered"]

    assert SUMMARY_HEADER_UZ in text
    assert "120" in text                 # approximate sold
    assert "4,500,000" in text           # estimated revenue
    assert NOTE_UZ in text               # localized permission note
    assert "Jami: 0" not in text         # no authoritative zeroed order totals


def test_daily_orders_present_unchanged(monkeypatch):
    monkeypatch.setattr(mm, "get_user", _aret(USER))
    monkeypatch.setattr(mm, "get_fbs_orders", _aret(ORDERS))
    monkeypatch.setattr(mm, "get_products", _aret(PRODUCTS))
    monkeypatch.setattr(mm, "get_sales_stats_from_products", _aret(STATS))
    monkeypatch.setattr(mm, "get_finance_orders", _aret(FINANCE))

    store = {}
    _run(mm.cmd_report_today(FakeMessage(store)))
    text = store["rendered"]

    assert "Jami: 1" in text                       # full order-based report
    assert "Komissiya" in text                     # finance overlay present
    assert NOTE_UZ not in text                      # no fallback note injected
    assert SUMMARY_HEADER_UZ not in text


def test_daily_non_403_product_failure_no_fallback(monkeypatch):
    monkeypatch.setattr(mm, "get_user", _aret(USER))
    monkeypatch.setattr(mm, "get_fbs_orders", _aret([]))
    monkeypatch.setattr(mm, "get_products", _aret(PRODUCTS))
    monkeypatch.setattr(mm, "get_sales_stats_from_products", _aret({}))  # {} => unavailable
    monkeypatch.setattr(mm, "get_finance_orders", _aret({}))

    store = {}
    _run(mm.cmd_report_today(FakeMessage(store)))
    text = store["rendered"]

    assert NOTE_UZ not in text
    assert "Jami: 0" in text             # existing zeroed report preserved
