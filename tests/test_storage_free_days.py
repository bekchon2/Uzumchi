"""
Storage free-days countdown tests (Fix C).

Property 1: Bug Condition — Storage Free-Days Countdown
            `cmd_storage` must render `free_days_left = max(0, FREE_DAYS - days_stored)`
            per invoice (additive to the existing stock view) and flag near-limit items;
            when invoices are empty/403 it renders the stock view + an "unavailable" note.
Property 5: Preservation — the out/low/warn/ok stock groupings are unchanged.
Validates: Requirements 1.1, 1.2, 2.1, 2.2, 3.1, 3.10
"""
import asyncio
import datetime

import handlers.main_menu as mm


def _aret(value):
    async def _inner(*args, **kwargs):
        return value
    return _inner


class _SentMessage:
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
    def __init__(self, store, uid=1):
        self.from_user = _FakeUser(uid)
        self._store = store

    async def answer(self, text, **kwargs):
        self._store.setdefault("loading", []).append(text)
        return _SentMessage(self._store)


def _run(coro):
    return asyncio.run(coro)


def _ms_days_ago(days: int) -> int:
    dt = datetime.datetime.now() - datetime.timedelta(days=days, hours=1)
    return int(dt.timestamp() * 1000)


USER = {"api_key": "key", "shop_id": 123, "lang": "ru", "shop_name": "JoyKid"}

# Products spanning every stock bucket: out(0) / low(<=5) / warn(6-15) / ok(>15).
PRODUCTS = [
    {"title": "Out item", "skuList": [{"quantityActive": 0, "price": 50000}]},
    {"title": "Low item", "skuList": [{"quantityActive": 3, "price": 60000}]},
    {"title": "Warn item", "skuList": [{"quantityActive": 10, "price": 70000}]},
    {"title": "Ok item", "skuList": [{"quantityActive": 25, "price": 80000}]},
]

# Two ACCEPTED invoices: 43 days (free_days_left=17, ok) and 58 days (free_days_left=2, alert).
INVOICES = [
    {
        "id": 9001,
        "invoiceNumber": 5001,
        "dateAccepted": _ms_days_ago(43),
        "totalAccepted": 88,
        "invoiceStatus": {"value": "ACCEPTED"},
    },
    {
        "id": 9002,
        "invoiceNumber": 5002,
        "dateAccepted": _ms_days_ago(58),
        "totalAccepted": 99,
        "invoiceStatus": {"value": "ACCEPTED"},
    },
]


# ─── Bug Condition (Property 1) ──────────────────────────────────────────────

def test_storage_renders_free_days_countdown(monkeypatch):
    """Property 1 — free-days countdown (17 and 2) is rendered and the near-limit
    invoice is flagged. FAILS on unfixed code (no free-storage section)."""
    monkeypatch.setattr(mm, "get_user", _aret(USER))
    monkeypatch.setattr(mm, "get_products", _aret(PRODUCTS))
    monkeypatch.setattr(mm, "get_invoices", _aret(INVOICES), raising=False)

    store = {}
    _run(mm.cmd_storage(FakeMessage(store)))
    text = store["rendered"]

    # free_days_left = max(0, 60 - days_stored): 60-43=17, 60-58=2
    assert "17 дн" in text          # 43-day invoice -> 17 free days remain
    assert "2 дн" in text           # 58-day invoice -> 2 free days remain
    assert "🚨" in text             # 58-day invoice flagged as near the limit


def test_storage_free_unavailable_when_no_invoices(monkeypatch):
    """Property 1 (edge) — empty invoices ([]/403) -> stock view + unavailable note,
    no crash, stock groupings preserved."""
    from locales.i18n import t

    monkeypatch.setattr(mm, "get_user", _aret(USER))
    monkeypatch.setattr(mm, "get_products", _aret(PRODUCTS))
    monkeypatch.setattr(mm, "get_invoices", _aret([]), raising=False)

    store = {}
    _run(mm.cmd_storage(FakeMessage(store)))
    text = store["rendered"]

    assert t("storage_free_unavailable", "ru") in text
    assert "Состояние склада" in text   # stock view still present


# ─── Preservation (Property 5) ───────────────────────────────────────────────

def test_storage_stock_groupings_preserved(monkeypatch):
    """Property 5 — the out/low/warn/ok groupings render unchanged (additive fix).
    Passes on unfixed code and after the fix (get_invoices -> [] keeps groupings)."""
    monkeypatch.setattr(mm, "get_user", _aret(USER))
    monkeypatch.setattr(mm, "get_products", _aret(PRODUCTS))
    monkeypatch.setattr(mm, "get_invoices", _aret([]), raising=False)

    store = {}
    _run(mm.cmd_storage(FakeMessage(store)))
    text = store["rendered"]

    assert "Состояние склада (FBS)" in text
    assert "Закончились" in text        # out bucket
    assert "Мало" in text               # low bucket
    assert "Внимание" in text           # warn bucket
    assert "Хороший запас" in text      # ok bucket
