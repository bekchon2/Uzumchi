"""
Competitor proxy + manual-price fallback tests (Fix D).

Property 3: Bug Condition — Competitor Price Always Shown
  (a) a blocked auto-fetch (price_source == "none") routes the user into a manual
      price prompt (CompetitorStates.waiting_manual_price) instead of dead-ending;
  (b) UZUM_PROXY is forwarded as aiohttp `proxy=` in both GET helpers.
Property 5: Preservation — auto-price path renders + clears as before; proxy-off
  equivalence (proxy=None when UZUM_PROXY is unset).
Validates: Requirements 1.5, 1.6, 1.7, 2.5, 2.6, 2.7, 3.9, 3.10
"""
import asyncio

import pytest

import handlers.main_menu as mm
import services.competitor_monitor as c
import database
from locales.i18n import t


# ─── Async helpers / doubles ─────────────────────────────────────────────────

def _run(coro):
    return asyncio.run(coro)


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
    def __init__(self, store, text="", uid=1):
        self.from_user = _FakeUser(uid)
        self.text = text
        self._store = store

    async def answer(self, text, **kwargs):
        self._store["answered"] = text
        return _SentMessage(self._store)


class FakeState:
    def __init__(self):
        self._state = None
        self._data = {}

    async def set_state(self, s):
        self._state = s

    async def get_state(self):
        return self._state

    async def update_data(self, **kw):
        self._data.update(kw)

    async def get_data(self):
        return dict(self._data)

    async def clear(self):
        self._state = None
        self._data = {}


USER = {"api_key": "key", "shop_id": 123, "lang": "ru", "shop_name": "JoyKid"}
URL = "https://uzum.uz/ru/product/test-2855035"


# ─── Fake aiohttp for proxy forwarding ───────────────────────────────────────

class _FakeResp:
    status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def text(self):
        return "<html>ok</html>"

    async def json(self, **k):
        return {}


def _make_fake_session(captured):
    class _FakeSession:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def get(self, url, **kwargs):
            captured.append(kwargs.get("proxy"))
            return _FakeResp()

    return _FakeSession


# ─── Bug Condition (Property 3a): manual fallback ────────────────────────────

def test_blocked_url_enters_manual_price_state(monkeypatch):
    """Property 3 — price_source == 'none' -> transition to waiting_manual_price
    and prompt for a manual price. FAILS on unfixed code (no such state/prompt)."""
    monkeypatch.setattr(mm, "get_user", _aret(USER))
    monkeypatch.setattr(mm, "get_products", _aret([]))
    monkeypatch.setattr(database, "add_product_url", _aret(None))
    blocked = {"title": "Blocked Item", "min_price": 0, "max_price": 0,
               "price_source": "none", "html_only": True}
    monkeypatch.setattr(c, "get_product_info_by_url", _aret(blocked))

    store = {}
    state = FakeState()
    _run(mm.competitor_url_received(FakeMessage(store, text=URL), state))

    assert _run(state.get_state()) == mm.CompetitorStates.waiting_manual_price
    assert t("competitor_manual_prompt", "ru") in store["rendered"]


# ─── Bug Condition (Property 3b): proxy forwarding ───────────────────────────

def test_fetch_html_forwards_proxy_when_set(monkeypatch):
    """Property 3 — UZUM_PROXY is forwarded to session.get in _fetch_product_html.
    FAILS on unfixed code (proxy kwarg never passed -> captured None)."""
    captured = []
    monkeypatch.setenv("UZUM_PROXY", "http://uzproxy:3128")
    monkeypatch.setattr(c.aiohttp, "ClientSession", _make_fake_session(captured))

    _run(c._fetch_product_html(URL))
    assert captured and captured[0] == "http://uzproxy:3128"


def test_api_fetch_forwards_proxy_when_set(monkeypatch):
    """Property 3 — UZUM_PROXY is forwarded to session.get in _get_product_from_api."""
    captured = []
    monkeypatch.setenv("UZUM_PROXY", "http://uzproxy:3128")
    monkeypatch.setattr(c.aiohttp, "ClientSession", _make_fake_session(captured))
    monkeypatch.setattr(c.asyncio, "sleep", _aret(None))  # skip the throttle delays

    _run(c._get_product_from_api("2855035"))
    assert captured and all(p == "http://uzproxy:3128" for p in captured)


# ─── Preservation (Property 5): auto-price path + proxy-off ──────────────────

def test_auto_price_path_renders_and_clears(monkeypatch):
    """Property 5 — when price is found (api), the report renders and state clears;
    the manual fallback is NOT entered. Passes on unfixed and fixed code."""
    monkeypatch.setattr(mm, "get_user", _aret(USER))
    monkeypatch.setattr(mm, "get_products", _aret([]))
    monkeypatch.setattr(database, "add_product_url", _aret(None))
    found = {"title": "Found Item", "min_price": 200000, "max_price": 250000,
             "price": 225000, "price_source": "api", "shop": "S",
             "rating": 0, "reviews": 0}
    monkeypatch.setattr(c, "get_product_info_by_url", _aret(found))

    store = {}
    state = FakeState()
    _run(mm.competitor_url_received(FakeMessage(store, text=URL), state))

    assert _run(state.get_state()) is None          # state cleared
    assert "200,000" in store["rendered"]           # price block rendered
    assert "Сохранено" in store["rendered"]


def test_proxy_off_equivalence_html(monkeypatch):
    """Property 5 — with UZUM_PROXY unset, _fetch_product_html passes proxy=None
    (equivalent to today's absent kwarg). Passes on unfixed and fixed code."""
    captured = []
    monkeypatch.delenv("UZUM_PROXY", raising=False)
    monkeypatch.setattr(c.aiohttp, "ClientSession", _make_fake_session(captured))

    _run(c._fetch_product_html(URL))
    assert captured and captured[0] is None


# ─── Manual-price handler (Property 3, task 12.5) ────────────────────────────

def test_manual_price_handler_saves_and_renders(monkeypatch):
    """Numeric manual price -> add_product_url called + report rendered with the
    entered value as the competitor (min/max) price; state cleared."""
    monkeypatch.setattr(mm, "get_user", _aret(USER))
    saved = {}

    async def _save(**kwargs):
        saved.update(kwargs)

    monkeypatch.setattr(database, "add_product_url", _save)

    state = FakeState()
    _run(state.update_data(pending_name="Blocked Item", pending_url=URL, my_price=180000.0))
    _run(state.set_state(mm.CompetitorStates.waiting_manual_price))

    store = {}
    _run(mm.competitor_manual_price_received(FakeMessage(store, text="150 000"), state))

    assert saved.get("product_name") == "Blocked Item"
    assert saved.get("uzum_url") == URL
    assert "150,000" in store["answered"]      # entered competitor price rendered
    assert _run(state.get_state()) is None     # state cleared


def test_manual_price_handler_rejects_non_numeric(monkeypatch):
    """Non-numeric input -> localized re-prompt, stays in state, no save."""
    monkeypatch.setattr(mm, "get_user", _aret(USER))

    async def _boom(**kwargs):
        raise AssertionError("must not save on invalid input")

    monkeypatch.setattr(database, "add_product_url", _boom)

    state = FakeState()
    _run(state.update_data(pending_name="Blocked Item", pending_url=URL, my_price=0.0))
    _run(state.set_state(mm.CompetitorStates.waiting_manual_price))

    store = {}
    _run(mm.competitor_manual_price_received(FakeMessage(store, text="abc"), state))

    assert t("competitor_manual_invalid", "ru") in store["answered"]
    assert _run(state.get_state()) == mm.CompetitorStates.waiting_manual_price


def test_manual_price_handler_cancel(monkeypatch):
    """Cancel text (🔙 Назад) clears state and returns without saving."""
    monkeypatch.setattr(mm, "get_user", _aret(USER))

    async def _boom(**kwargs):
        raise AssertionError("must not save on cancel")

    monkeypatch.setattr(database, "add_product_url", _boom)

    state = FakeState()
    _run(state.set_state(mm.CompetitorStates.waiting_manual_price))

    store = {}
    _run(mm.competitor_manual_price_received(FakeMessage(store, text="🔙 Назад"), state))
    assert _run(state.get_state()) is None
