"""
Tests for the sku_snapshots persistence helpers in database.py.

Feature: products-daily-sale-notifications
Property 9: Snapshot upsert round-trip (and idempotence)
"""
import asyncio
import importlib

import pytest

import database

try:
    from hypothesis import given, strategies as st, settings, HealthCheck
    HAS_HYPOTHESIS = True
except ImportError:  # pragma: no cover
    HAS_HYPOTHESIS = False


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    """Point database.DB_PATH at a fresh temp sqlite file and init the schema."""
    db_file = tmp_path / "test_snapshots.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_file))
    asyncio.run(database.init_db())
    return str(db_file)


def test_empty_store_returns_empty_dict(temp_db):
    assert asyncio.run(database.get_sku_snapshots(1, 99)) == {}


def test_round_trip_basic(temp_db):
    asyncio.run(database.save_sku_snapshots(1, 99, {"1001": 7, "1002": 3}))
    got = asyncio.run(database.get_sku_snapshots(1, 99))
    assert got == {"1001": 7, "1002": 3}


def test_keys_coerced_to_str_values_to_int(temp_db):
    asyncio.run(database.save_sku_snapshots(1, 99, {1001: 7, 1002: "3"}))
    got = asyncio.run(database.get_sku_snapshots(1, 99))
    assert got == {"1001": 7, "1002": 3}
    assert all(isinstance(k, str) for k in got)
    assert all(isinstance(v, int) for v in got.values())


def test_upsert_updates_existing(temp_db):
    asyncio.run(database.save_sku_snapshots(1, 99, {"1001": 7}))
    asyncio.run(database.save_sku_snapshots(1, 99, {"1001": 4}))
    assert asyncio.run(database.get_sku_snapshots(1, 99)) == {"1001": 4}


def test_idempotent_repeated_save(temp_db):
    mapping = {"1001": 7, "1002": 3}
    for _ in range(3):
        asyncio.run(database.save_sku_snapshots(1, 99, mapping))
    assert asyncio.run(database.get_sku_snapshots(1, 99)) == mapping


def test_no_leak_between_shops_and_users(temp_db):
    asyncio.run(database.save_sku_snapshots(1, 99, {"a": 1}))
    asyncio.run(database.save_sku_snapshots(1, 100, {"b": 2}))
    asyncio.run(database.save_sku_snapshots(2, 99, {"c": 3}))
    assert asyncio.run(database.get_sku_snapshots(1, 99)) == {"a": 1}
    assert asyncio.run(database.get_sku_snapshots(1, 100)) == {"b": 2}
    assert asyncio.run(database.get_sku_snapshots(2, 99)) == {"c": 3}


def test_empty_mapping_save_is_noop(temp_db):
    asyncio.run(database.save_sku_snapshots(1, 99, {}))
    assert asyncio.run(database.get_sku_snapshots(1, 99)) == {}


if HAS_HYPOTHESIS:

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        mapping=st.dictionaries(
            keys=st.one_of(
                st.integers(min_value=1, max_value=10_000_000),
                st.text(min_size=1, max_size=12),
            ),
            values=st.integers(min_value=0, max_value=100_000),
            max_size=20,
        )
    )
    def test_property_round_trip_and_idempotence(temp_db, mapping):
        """Property 9: save then read yields equal mapping (str keys, int values);
        repeated unchanged saves are idempotent."""
        expected = {str(k): int(v) for k, v in mapping.items()}
        asyncio.run(database.save_sku_snapshots(5, 5, mapping))
        first = asyncio.run(database.get_sku_snapshots(5, 5))
        # every saved pair is present with the expected value
        for k, v in expected.items():
            assert first[k] == v
        # repeated save is idempotent for unchanged values
        asyncio.run(database.save_sku_snapshots(5, 5, mapping))
        second = asyncio.run(database.get_sku_snapshots(5, 5))
        for k, v in expected.items():
            assert second[k] == v
