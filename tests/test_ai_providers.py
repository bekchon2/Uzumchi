"""
AI provider selection / dispatch tests (env-based).

Bugfix Fix A: provider env vars must be read at CALL TIME (inside
`_all_providers()` / `_select_providers()`), not captured into module-level
constants at import time. These tests drive selection via the *environment*
(`monkeypatch.setenv` / `monkeypatch.delenv`) rather than patching module
constants, which is the contract after the fix.

Property 4: Bug Condition — AI Reads Env At Call Time
Property 5: Preservation — AI selection semantics unchanged
Validates: Requirements 1.8, 1.9, 2.8, 2.9, 3.8, 3.10
"""
import asyncio
import importlib

import pytest

import services.gemini_ai as g

_PROVIDER_ENV = ["GROQ_API_KEY", "OPENROUTER_API_KEY", "GEMINI_API_KEY", "AI_PROVIDER",
                 "GROQ_MODEL", "OPENROUTER_MODEL", "GEMINI_MODEL"]


def _set_env(monkeypatch, **keys):
    """Clear all provider env vars, set the supplied ones, then reload the module.

    Reloading after the env is set keeps the preservation tests valid on BOTH the
    UNFIXED code (which captures constants at import time) and the FIXED code
    (which reads env at call time): in either case the configured providers are
    visible by the time the assertions run.
    """
    for var in _PROVIDER_ENV:
        monkeypatch.delenv(var, raising=False)
    for k, v in keys.items():
        monkeypatch.setenv(k, v)
    importlib.reload(g)


# ─── Bug Condition (Property 4): env set AFTER import is honored ──────────────

def test_env_set_after_import_is_picked_up(monkeypatch):
    """Property 4 — a provider key exported AFTER the module is imported must
    still be selected (env read at call time, not at import time).

    On UNFIXED code this FAILS: the module captured GROQ_API_KEY == "" at import
    so _select_providers() returns [] despite the populated environment.
    Counterexample: GROQ_API_KEY set after import -> _select_providers() == []
    instead of ['groq'].
    """
    # Clear all provider env BEFORE (re)importing the module.
    for var in _PROVIDER_ENV:
        monkeypatch.delenv(var, raising=False)
    importlib.reload(g)

    # Populate the env AFTER import.
    monkeypatch.setenv("GROQ_API_KEY", "x")

    names = [p.name for p in g._select_providers()]
    assert names == ["groq"]


# ─── Provider selection (Property 5 preservation) ────────────────────────────

def test_select_empty_when_no_key(monkeypatch):
    _set_env(monkeypatch)
    assert g._select_providers() == []


def test_select_default_priority_order(monkeypatch):
    _set_env(monkeypatch, GEMINI_API_KEY="gkey", OPENROUTER_API_KEY="okey", GROQ_API_KEY="qkey")
    names = [p.name for p in g._select_providers()]
    assert names == ["groq", "openrouter", "gemini"]


def test_select_filters_to_configured(monkeypatch):
    _set_env(monkeypatch, OPENROUTER_API_KEY="okey", GEMINI_API_KEY="gkey")
    names = [p.name for p in g._select_providers()]
    assert names == ["openrouter", "gemini"]  # groq absent


def test_ai_provider_override_returns_single(monkeypatch):
    _set_env(monkeypatch, GROQ_API_KEY="qkey", GEMINI_API_KEY="gkey", AI_PROVIDER="gemini")
    selected = g._select_providers()
    assert [p.name for p in selected] == ["gemini"]


def test_ai_provider_override_ignored_when_key_missing(monkeypatch):
    _set_env(monkeypatch, GROQ_API_KEY="qkey", AI_PROVIDER="gemini")  # no gemini key
    # Falls back to default order over configured providers.
    assert [p.name for p in g._select_providers()] == ["groq"]


def test_non_aizasy_key_accepted(monkeypatch):
    """A key not starting with 'AIzaSy' is still usable."""
    _set_env(monkeypatch, GEMINI_API_KEY="sk-not-aizasy-format")
    providers = g._select_providers()
    assert len(providers) == 1 and providers[0].name == "gemini"
    assert providers[0].api_key == "sk-not-aizasy-format"


def test_default_models_used(monkeypatch):
    """Default model names are applied when *_MODEL env vars are unset."""
    _set_env(monkeypatch, GROQ_API_KEY="qkey", OPENROUTER_API_KEY="okey", GEMINI_API_KEY="gkey")
    cfgs = {p.name: p for p in g._select_providers()}
    assert cfgs["groq"].model == "llama-3.3-70b-versatile"
    assert cfgs["openrouter"].model == "meta-llama/llama-3.3-70b-instruct"
    assert cfgs["gemini"].model == "gemini-1.5-flash"


def test_model_override_from_env(monkeypatch):
    """*_MODEL env vars override the defaults at call time."""
    _set_env(monkeypatch, GROQ_API_KEY="qkey", GROQ_MODEL="custom-groq-model")
    cfgs = {p.name: p for p in g._select_providers()}
    assert cfgs["groq"].model == "custom-groq-model"


# ─── Dispatch (Property 5 preservation) ──────────────────────────────────────

def test_no_key_returns_localized_and_no_network(monkeypatch):
    """No key => localized message, no provider call attempted."""
    _set_env(monkeypatch)

    async def _boom(*a, **k):
        raise AssertionError("network call must not happen")

    monkeypatch.setattr(g, "_call_openai_compatible", _boom)
    monkeypatch.setattr(g, "_call_gemini", _boom)

    ru = asyncio.run(g.ask_gemini("hi", "ru"))
    uz = asyncio.run(g.ask_gemini("hi", "uz"))
    assert ru and "не настроен" in ru
    assert uz and "sozlanmagan" in uz


def test_success_returns_first_provider_answer(monkeypatch):
    _set_env(monkeypatch, GROQ_API_KEY="qkey", OPENROUTER_API_KEY="okey")

    calls = []

    async def _ok(cfg, prompt):
        calls.append(cfg.name)
        return f"answer-from-{cfg.name}"

    monkeypatch.setattr(g, "_call_openai_compatible", _ok)
    out = asyncio.run(g.ask_gemini("hi", "ru"))
    assert out == "answer-from-groq"
    assert calls == ["groq"]  # second provider never tried


def test_fallback_to_next_provider(monkeypatch):
    """First provider failing triggers the next one."""
    _set_env(monkeypatch, GROQ_API_KEY="qkey", OPENROUTER_API_KEY="okey")

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
    _set_env(monkeypatch, GROQ_API_KEY="qkey", OPENROUTER_API_KEY="okey")

    async def _resp(cfg, prompt):
        return "" if cfg.name == "groq" else "real-answer"

    monkeypatch.setattr(g, "_call_openai_compatible", _resp)
    out = asyncio.run(g.ask_gemini("hi", "ru"))
    assert out == "real-answer"


def test_all_providers_fail_localized_error(monkeypatch):
    """All providers failing returns a non-empty localized error."""
    _set_env(monkeypatch, GROQ_API_KEY="qkey")

    async def _fail(cfg, prompt):
        raise RuntimeError("down")

    monkeypatch.setattr(g, "_call_openai_compatible", _fail)
    ru = asyncio.run(g.ask_gemini("hi", "ru"))
    uz = asyncio.run(g.ask_gemini("hi", "uz"))
    assert ru and "не ответил" in ru
    assert uz and "javob bermadi" in uz


def test_ask_gemini_real_answer_with_env_set_after_import(monkeypatch):
    """Property 4 — with env populated after import and a stubbed transport,
    ask_gemini returns a real completion (not the 'not configured' message)."""
    for var in _PROVIDER_ENV:
        monkeypatch.delenv(var, raising=False)
    importlib.reload(g)
    monkeypatch.setenv("GROQ_API_KEY", "qkey")

    async def _ok(cfg, prompt):
        return "real groq completion"

    monkeypatch.setattr(g, "_call_openai_compatible", _ok)
    out = asyncio.run(g.ask_gemini("hi", "ru"))
    assert out == "real groq completion"
    assert "не настроен" not in out


def test_prompt_builders_signatures_intact():
    """Prompt builders kept call-site compatible."""
    importlib.reload(g)
    assert g.build_sales_analysis_prompt({}, [], "ru")
    assert g.build_storage_advice_prompt([], "ru")
    assert g.build_competitor_advice_prompt("x", 100, 200, 150, "ru")
