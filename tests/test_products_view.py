"""
Tests for the active-only single-page products view in handlers/main_menu.py.

Feature: products-daily-sale-notifications
Property 3: Chunking loses no products
Property 4: Chunk size bound
Property 5: Products view emits no page buttons
"""
import asyncio

import pytest

import handlers.main_menu as mm
from handlers.main_menu import build_chunks, TG_CHUNK_LIMIT

try:
    from hypothesis import given, strategies as st, settings
    HAS_HYPOTHESIS = True
except ImportError:  # pragma: no cover
    HAS_HYPOTHESIS = False


# ─── build_chunks unit tests ──────────────────────────────────────────────────

def test_build_chunks_empty_blocks_returns_header_only():
    assert build_chunks("HEADER", []) == ["HEADER"]


def test_build_chunks_header_only_in_first_chunk():
    blocks = ["x" * 2000, "y" * 2000]
    chunks = build_chunks("HEADER", blocks, limit=3500)
    assert chunks[0].startswith("HEADER")
    assert all(not c.startswith("HEADER") for c in chunks[1:])


def test_build_chunks_oversized_single_block_own_message():
    big = "z" * 5000
    chunks = build_chunks("H", [big], limit=3500)
    # header chunk + the oversized block as its own message
    assert big in chunks
    assert any(len(c) > 3500 for c in chunks)


def test_build_chunks_order_preserved_concat():
    blocks = [f"b{i}" for i in range(10)]
    chunks = build_chunks("", blocks, limit=10)
    joined = "\n\n".join(chunks)
    for b in blocks:
        assert b in joined
    # order preserved
    positions = [joined.index(b) for b in blocks]
    assert positions == sorted(positions)


# ─── Property tests for build_chunks (Tasks 3.3 / 3.4) ────────────────────────

if HAS_HYPOTHESIS:
    # Blocks drawn from an alphabet WITHOUT the "\n\n" join separator so the test
    # can reconstruct the original sequence unambiguously. Headers are kept small
    # (<= min limit) so the header is never itself an over-limit chunk — the only
    # documented over-limit case is a single oversized product block.
    _block = st.text(
        alphabet=st.characters(min_codepoint=33, max_codepoint=126),
        min_size=1, max_size=60,
    )
    _header = st.text(
        alphabet=st.characters(min_codepoint=33, max_codepoint=126),
        max_size=8,
    )

    @settings(max_examples=200)
    @given(
        header=_header,
        blocks=st.lists(_block, max_size=30),
        limit=st.integers(min_value=10, max_value=120),
    )
    def test_property_chunking_loses_no_products(header, blocks, limit):
        """Property 3: ordered concatenation of blocks is preserved across chunks."""
        chunks = build_chunks(header, blocks, limit=limit)
        # Reconstruct the block sequence: strip the header from the first chunk,
        # then split every chunk on the "\n\n" join separator.
        recovered = []
        for i, c in enumerate(chunks):
            body = c
            if i == 0 and header:
                # header is the prefix of the first chunk (possibly the whole chunk)
                assert body.startswith(header)
                body = body[len(header):]
                if body.startswith("\n\n"):
                    body = body[2:]
                elif body == "":
                    continue
            recovered.extend(body.split("\n\n"))
        assert recovered == blocks

    @settings(max_examples=200)
    @given(
        header=_header,
        blocks=st.lists(_block, max_size=30),
        limit=st.integers(min_value=10, max_value=120),
    )
    def test_property_chunk_size_bound(header, blocks, limit):
        """Property 4: every chunk <= limit, except a single oversized block."""
        chunks = build_chunks(header, blocks, limit=limit)
        for c in chunks:
            if len(c) > limit:
                # An over-limit chunk must consist of a single original block.
                assert c in blocks


# ─── Products view tests (Task 3.5) ───────────────────────────────────────────

class FakeMessage:
    def __init__(self):
        self.answers = []  # list of (text, reply_markup)

    async def answer(self, text, reply_markup=None, parse_mode=None):
        self.answers.append((text, reply_markup))
        return self


class FakeLoadingMsg:
    def __init__(self):
        self.edits = []  # list of (text, reply_markup)

    async def edit_text(self, text, reply_markup=None, parse_mode=None):
        self.edits.append((text, reply_markup))
        return self


def _run_view(monkeypatch, products):
    async def fake_get_products(api_key, shop_id):
        return products

    monkeypatch.setattr(mm, "get_products", fake_get_products)
    message = FakeMessage()
    msg = FakeLoadingMsg()
    user = {"api_key": "k", "shop_id": 1, "lang": "ru"}
    asyncio.run(mm._show_products_page(message, msg, user, "ru"))
    return message, msg


def _product(title, qty, **extra):
    p = {"title": title, "skuList": [{"quantityActive": qty, "skuId": title}]}
    p.update(extra)
    return p


def test_view_no_page_buttons(monkeypatch):
    products = [_product(f"P{i}", 10) for i in range(20)]
    message, msg = _run_view(monkeypatch, products)
    # No reply_markup on any produced message (edit or answer)
    for _, kb in msg.edits:
        assert kb is None
    for _, kb in message.answers:
        assert kb is None


def test_view_active_only(monkeypatch):
    products = [
        _product("Active1", 10),
        _product("Archived", 5, status="ARCHIVED"),
        _product("Active2", 3),
        _product("Inactive", 2, isActive=False),
    ]
    message, msg = _run_view(monkeypatch, products)
    rendered = "".join(t for t, _ in msg.edits) + "".join(t for t, _ in message.answers)
    assert "Active1" in rendered
    assert "Active2" in rendered
    assert "Archived" not in rendered
    assert "Inactive" not in rendered


def test_view_header_counts_active_only(monkeypatch):
    products = [
        _product("Active1", 10),
        _product("Active2", 3),
        _product("Archived", 99, status="DELETED"),
    ]
    message, msg = _run_view(monkeypatch, products)
    header = msg.edits[0][0]
    # 2 active products, total active stock 13
    assert "2" in header
    assert "13" in header


def test_view_all_inactive_renders_no_data(monkeypatch):
    products = [
        _product("Archived", 5, status="ARCHIVED"),
        _product("Inactive", 2, isActive=False),
    ]
    message, msg = _run_view(monkeypatch, products)
    from locales.i18n import t
    rendered = "".join(tx for tx, _ in msg.edits)
    assert rendered == t("no_data", "ru")


def test_view_empty_renders_no_data(monkeypatch):
    message, msg = _run_view(monkeypatch, [])
    from locales.i18n import t
    rendered = "".join(tx for tx, _ in msg.edits)
    assert rendered == t("no_data", "ru")
