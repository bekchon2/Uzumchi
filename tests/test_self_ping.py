"""
self_ping() must be a safe no-op (return immediately, no loop, no raise) when
RENDER_EXTERNAL_URL is unset.
"""
import asyncio

import main


def test_self_ping_noop_when_url_unset(monkeypatch):
    # Force "local mode" regardless of the real environment.
    monkeypatch.setattr(main, "RENDER_URL", "", raising=False)

    # Should return promptly without entering the ping loop. A generous timeout
    # guards against a regression that would start sleeping/looping.
    asyncio.run(asyncio.wait_for(main.self_ping(), timeout=2))


def test_ping_health_handlers_unchanged():
    # Endpoints preserved: /ping -> "pong", /health -> "OK".
    class FakeReq:
        pass

    pong = asyncio.run(main.ping_handler(FakeReq()))
    ok = asyncio.run(main.health_handler(FakeReq()))
    assert pong.text == "pong"
    assert ok.text == "OK"
