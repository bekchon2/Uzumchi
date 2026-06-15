"""
Tests for sale detection helpers and the mocked scheduler jobs.

Feature: products-daily-sale-notifications
Property 6: Sale detection iff strict decrease
Property 7: Increases and new SKUs never trigger a push
Property 8: First run establishes baseline silently
Property 10: SKUs without an id are skipped
Property 11: Daily digest counts are consistent
Property 12: Daily report is sent at most once per day
"""
import asyncio

import pytest

import database
import services.scheduler as sched
from services.scheduler import detect_sales, build_current_map

try:
    from hypothesis import given, strategies as st, settings
    HAS_HYPOTHESIS = True
except ImportError:  # pragma: no cover
    HAS_HYPOTHESIS = False


# ─── detect_sales / build_current_map unit tests ──────────────────────────────

def test_detect_sales_strict_decrease():
    assert detect_sales({"1001": 7}, {"1001": 5}) == [("1001", 2, 5)]


def test_detect_sales_increase_ignored():
    assert detect_sales({"1001": 7}, {"1001": 9}) == []


def test_detect_sales_unchanged_ignored():
    assert detect_sales({"1001": 7}, {"1001": 7}) == []


def test_detect_sales_new_sku_ignored():
    assert detect_sales({}, {"1001": 7}) == []
    assert detect_sales({"1001": 7}, {"1001": 5, "2002": 3}) == [("1001", 2, 5)]


def test_build_current_map_uses_skuid_then_id():
    products = [
        {"title": "A", "skuList": [{"skuId": 111, "quantityActive": 5}]},
        {"title": "B", "skuList": [{"id": 222, "quantityActive": 3}]},
    ]
    assert build_current_map(products) == {"111": 5, "222": 3}


def test_build_current_map_skips_idless_skus():
    products = [
        {"title": "A", "skuList": [{"quantityActive": 5}, {"skuId": 7, "quantityActive": 2}]},
    ]
    assert build_current_map(products) == {"7": 2}


# ─── Property tests (Tasks 5.4 / 5.5) ─────────────────────────────────────────

if HAS_HYPOTHESIS:
    _qty = st.integers(min_value=0, max_value=1000)
    _sid = st.sampled_from(["a", "b", "c", "d", "e"])

    @settings(max_examples=200)
    @given(prev=st.dictionaries(_sid, _qty), current=st.dictionaries(_sid, _qty))
    def test_property_detect_sales_iff_strict_decrease(prev, current):
        """Property 6 + 7."""
        events = detect_sales(prev, current)
        emitted = {sid for sid, _, _ in events}
        for sid, sold, remaining in events:
            assert sid in prev and sid in current
            assert prev[sid] > current[sid]
            assert sold == prev[sid] - current[sid] > 0
            assert remaining == current[sid]
        # completeness: every strict decrease present in both is emitted
        for sid in current:
            if sid in prev and prev[sid] > current[sid]:
                assert sid in emitted
            else:
                assert sid not in emitted

    @settings(max_examples=100)
    @given(
        skus=st.lists(
            st.fixed_dictionaries(
                {"quantityActive": _qty},
                optional={"skuId": st.integers(1, 1000), "id": st.integers(1, 1000)},
            ),
            max_size=8,
        )
    )
    def test_property_idless_skus_skipped(skus):
        """Property 10: SKUs lacking both skuId and id never enter the map."""
        products = [{"title": "P", "skuList": skus}]
        current = build_current_map(products)
        for sku in skus:
            sid = sku.get("skuId") or sku.get("id")
            if sid is None:
                # nothing with this shape should be present
                continue
        # every key in current corresponds to a sku that had an id
        n_with_id = sum(1 for s in skus if (s.get("skuId") or s.get("id")) is not None)
        # distinct ids may collapse; current size <= n_with_id
        assert len(current) <= n_with_id


# ─── Mocked job infrastructure ────────────────────────────────────────────────

class FakeBot:
    def __init__(self):
        self.sent = []  # list of (chat_id, text)

    async def send_message(self, chat_id, text, parse_mode=None):
        self.sent.append((chat_id, text))


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "sched.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_file))
    asyncio.run(database.init_db())
    return str(db_file)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(sched.asyncio, "sleep", _noop)


def _patch_users(monkeypatch, users):
    async def fake_get_all_users():
        return users
    monkeypatch.setattr(sched, "get_all_users", fake_get_all_users)


def _patch_products(monkeypatch, products):
    async def fake_get_products(api_key, shop_id):
        return products
    monkeypatch.setattr(sched, "get_products", fake_get_products)


USER = {"user_id": 42, "api_key": "k", "shop_id": 7, "lang": "ru"}


# ─── run_sale_check mocked tests (Task 5.6) ───────────────────────────────────

def test_sale_check_first_run_baseline_no_push(temp_db, monkeypatch):
    products = [{"title": "Cup", "skuList": [{"skuId": 1, "quantityActive": 10}]}]
    _patch_users(monkeypatch, [USER])
    _patch_products(monkeypatch, products)
    bot = FakeBot()
    asyncio.run(sched.run_sale_check(bot))
    assert bot.sent == []  # no push on first run
    # baseline stored equal to current active-sku map
    snap = asyncio.run(database.get_sku_snapshots(42, 7))
    assert snap == {"1": 10}


def test_sale_check_decrease_sends_one_push(temp_db, monkeypatch):
    _patch_users(monkeypatch, [USER])
    bot = FakeBot()

    # First run: baseline 10
    _patch_products(monkeypatch, [{"title": "Cup", "skuList": [{"skuId": 1, "quantityActive": 10}]}])
    asyncio.run(sched.run_sale_check(bot))
    assert bot.sent == []

    # Second run: dropped to 7 -> one push (sold 3, remaining 7)
    _patch_products(monkeypatch, [{"title": "Cup", "skuList": [{"skuId": 1, "quantityActive": 7}]}])
    asyncio.run(sched.run_sale_check(bot))
    assert len(bot.sent) == 1
    chat_id, text = bot.sent[0]
    assert chat_id == 42
    assert "Cup" in text
    assert "3" in text and "7" in text
    # snapshot updated
    assert asyncio.run(database.get_sku_snapshots(42, 7)) == {"1": 7}


def test_sale_check_increase_no_push(temp_db, monkeypatch):
    _patch_users(monkeypatch, [USER])
    bot = FakeBot()
    _patch_products(monkeypatch, [{"title": "Cup", "skuList": [{"skuId": 1, "quantityActive": 5}]}])
    asyncio.run(sched.run_sale_check(bot))
    _patch_products(monkeypatch, [{"title": "Cup", "skuList": [{"skuId": 1, "quantityActive": 9}]}])
    asyncio.run(sched.run_sale_check(bot))
    assert bot.sent == []
    assert asyncio.run(database.get_sku_snapshots(42, 7)) == {"1": 9}


def test_sale_check_variant_in_push(temp_db, monkeypatch):
    _patch_users(monkeypatch, [USER])
    bot = FakeBot()
    sku = {
        "skuId": 1, "quantityActive": 10,
        "characteristicsList": [
            {"characteristicValue": {"ru": "Красный", "uz": "Qizil"}}
        ],
    }
    _patch_products(monkeypatch, [{"title": "Cup", "skuList": [dict(sku)]}])
    asyncio.run(sched.run_sale_check(bot))
    sku2 = dict(sku); sku2["quantityActive"] = 8
    _patch_products(monkeypatch, [{"title": "Cup", "skuList": [sku2]}])
    asyncio.run(sched.run_sale_check(bot))
    assert len(bot.sent) == 1
    assert "Красный" in bot.sent[0][1]


# ─── run_product_report mocked tests (Task 5.7) ───────────────────────────────

def test_product_report_counts_and_send(temp_db, monkeypatch):
    products = [
        {"title": "Full", "skuList": [{"skuId": 1, "quantityActive": 100}]},   # ok
        {"title": "Low", "skuList": [{"skuId": 2, "quantityActive": 3}]},      # low
        {"title": "Out", "skuList": [{"skuId": 3, "quantityActive": 0}]},      # out
        {"title": "Arch", "status": "ARCHIVED", "skuList": [{"skuId": 4, "quantityActive": 50}]},
    ]
    _patch_users(monkeypatch, [USER])
    _patch_products(monkeypatch, products)
    bot = FakeBot()
    asyncio.run(sched.run_product_report(bot))
    assert len(bot.sent) == 1
    text = bot.sent[0][1]
    # 3 active products, total stock 103, low 1, out 1
    assert "3" in text
    assert "103" in text
    # urgent items list contains Out and Low (archived excluded)
    assert "Out" in text
    assert "Low" in text
    assert "Arch" not in text


def test_product_report_dedupe_once_per_day(temp_db, monkeypatch):
    products = [{"title": "Full", "skuList": [{"skuId": 1, "quantityActive": 100}]}]
    _patch_users(monkeypatch, [USER])
    _patch_products(monkeypatch, products)
    bot = FakeBot()
    asyncio.run(sched.run_product_report(bot))
    asyncio.run(sched.run_product_report(bot))  # second run same day
    assert len(bot.sent) == 1  # only one report sent


def test_product_report_skips_already_notified(temp_db, monkeypatch):
    products = [{"title": "Full", "skuList": [{"skuId": 1, "quantityActive": 100}]}]
    _patch_users(monkeypatch, [USER])
    _patch_products(monkeypatch, products)
    bot = FakeBot()
    # Pre-mark as notified today
    asyncio.run(database.log_notification(42, "product_report"))
    asyncio.run(sched.run_product_report(bot))
    assert bot.sent == []
