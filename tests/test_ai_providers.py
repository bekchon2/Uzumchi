"""
Change 3 tests — multi-provider AI selection and dispatch.

Property 8: Provider ordering
Property 9: No-key behavior
Property 10: Fallback dispatch
Property 11: Key-format liberty
Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4
"""
import asyncio

import pytest

import services.gemini_ai as g


def _clear_keys(monkeypatch):
    monkeypatch.setattr(g, "GROQ_API_KEY", "")
    monkeypatch.setattr(g, "OPENROUTER_API_KEY", "")
    monkeypatch.setattr(g, "GEMINI_API_KEY", "")
    monkeypatch.setattr(g, "AI_PROVIDER", "")


# ─── Provider selection (Property 8, 11) ─────────────────────────────────────

def test_select_empty_when_no_key(monkeypatch):
    _clear_keys(monkeypatch)
    assert g._select_providers() == []


def test_select_default_priority_order(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setattr(g, "GEMINI_API_KEY", "gkey")
    monkeypatch.setattr(g, "OPENROUTER_API_KEY", "okey")
    monkeypatch.setattr(g, "GROQ_API_KEY", "qkey")
    names = [p.name for p in g._select_providers()]
    assert names == ["groq", "openrouter", "gemini"]


def test_select_filters_to_configured(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setattr(g, "OPENROUTER_API_KEY", "okey")
    monkeypatch.setattr(g, "GEMINI_API_KEY", "gkey")
    names = [p.name for p in g._select_providers()]
    assert names == ["openrouter", "gemini"]  # groq absent


def test_ai_provider_override_returns_single(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setattr(g, "GROQ_API_KEY", "qkey")
    monkeypatch.setattr(g, "GEMINI_API_KEY", "gkey")
    monkeypatch.setattr(g, "AI_PROVIDER", "gemini")
    selected = g._select_providers()
    assert [p.name for p in selected] == ["gemini"]


def test_ai_provider_override_ignored_when_key_missing(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setattr(g, "GROQ_API_KEY", "qkey")
    monkeypatch.setattr(g, "AI_PROVIDER", "gemini")  # no gemini key
    # Falls back to default order over configured providers.
    assert [p.name for p in g._select_providers()] == ["groq"]


def test_non_aizasy_key_accepted(monkeypatch):
    """Property 11 — a key not starting with 'AIzaSy' is still usable."""
    _clear_keys(monkeypatch)
    monkeypatch.setattr(g, "GEMINI_API_KEY", "sk-not-aizasy-format")
    providers = g._select_providers()
    assert len(providers) == 1 and providers[0].name == "gemini"
    assert providers[0].api_key == "sk-not-aizasy-format"


# ─── Dispatch (Property 9, 10) ───────────────────────────────────────────────

def test_no_key_returns_localized_and_no_network(monkeypatch):
    """Property 9 — no key => localized message, no provider call attempted."""
    _clear_keys(monkeypatch)

    async def _boom(*a, **k):
        raise AssertionError("network call must not happen")

    monkeypatch.setattr(g, "_call_openai_compatible", _boom)
    monkeypatch.setattr(g, "_call_gemini", _boom)

    ru = asyncio.run(g.ask_gemini("hi", "ru"))
    uz = asyncio.run(g.ask_gemini("hi", "uz"))
    assert ru and "не настроен" in ru
    assert uz and "sozlanmagan" in uz


def test_success_returns_first_provider_answer(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setattr(g, "GROQ_API_KEY", "qkey")
    monkeypatch.setattr(g, "OPENROUTER_API_KEY", "okey")

    calls = []

    async def _ok(cfg, prompt):
        calls.append(cfg.name)
        return f"answer-from-{cfg.name}"

    monkeypatch.setattr(g, "_call_openai_compatible", _ok)
    out = asyncio.run(g.ask_gemini("hi", "ru"))
    assert out == "answer-from-groq"
    assert calls == ["groq"]  # second provider never tried


def test_fallback_to_next_provider(monkeypatch):
    """Property 10 — first provider failing triggers the next one."""
    _clear_keys(monkeypatch)
    monkeypatch.setattr(g, "GROQ_API_KEY", "qkey")
    monkeypatch.setattr(g, "OPENROUTER_API_KEY", "okey")

    calls = []

    async def _maybe(cfg, prompt):
        calls.append(cfg.name)
        if cfg.name == "groq":
            raise RuntimeError("groq down")
        return "answer-from-openrouter"

    monkeypatch.setattr(g, "_call_openai_compatible", _maybe)
    out = asyncio.run(g.ask_gemini("hi", "ru"))
    assert out == "answer-from-openrouter"
    assert calls == ["groq", "openrouter"]


def test_empty_response_falls_through(monkeypatch):
    """Empty answer from first provider => next provider attempted."""
    _clear_keys(monkeypatch)
    monkeypatch.setattr(g, "GROQ_API_KEY", "qkey")
    monkeypatch.setattr(g, "OPENROUTER_API_KEY", "okey")

    async def _resp(cfg, prompt):
        return "" if cfg.name == "groq" else "real-answer"

    monkeypatch.setattr(g, "_call_openai_compatible", _resp)
    out = asyncio.run(g.ask_gemini("hi", "ru"))
    assert out == "real-answer"


def test_all_providers_fail_localized_error(monkeypatch):
    """Property — all providers failing returns a non-empty localized error."""
    _clear_keys(monkeypatch)
    monkeypatch.setattr(g, "GROQ_API_KEY", "qkey")

    async def _fail(cfg, prompt):
        raise RuntimeError("down")

    monkeypatch.setattr(g, "_call_openai_compatible", _fail)
    ru = asyncio.run(g.ask_gemini("hi", "ru"))
    uz = asyncio.run(g.ask_gemini("hi", "uz"))
    assert ru and "не ответил" in ru
    assert uz and "javob bermadi" in uz


def test_prompt_builders_signatures_intact():
    """Requirements 4.8, 7.2 — prompt builders kept."""
    assert g.build_sales_analysis_prompt({}, [], "ru")
    assert g.build_storage_advice_prompt([], "ru")
    assert g.build_competitor_advice_prompt("x", 100, 200, 150, "ru")
