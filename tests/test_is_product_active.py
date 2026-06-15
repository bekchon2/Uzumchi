"""
Tests for services.uzum_api.is_product_active.

Feature: products-daily-sale-notifications
Property 1: Active filter excludes all inactive shapes
Property 2: Active filter default is fail-open
"""
import pytest

from services.uzum_api import is_product_active, ARCHIVED_STATUSES

try:
    from hypothesis import given, strategies as st, settings
    HAS_HYPOTHESIS = True
except ImportError:  # pragma: no cover
    HAS_HYPOTHESIS = False


# ─── Unit / example tests (Task 1.4) ──────────────────────────────────────────

@pytest.mark.parametrize("status", sorted(ARCHIVED_STATUSES))
def test_status_field_archived_is_inactive(status):
    assert is_product_active({"status": status}) is False


@pytest.mark.parametrize("status", sorted(ARCHIVED_STATUSES))
def test_product_status_field_archived_is_inactive(status):
    assert is_product_active({"productStatus": status}) is False


@pytest.mark.parametrize("raw", ["archived", "  Archived  ", "ArChIvEd", "moderation_failed"])
def test_status_casing_and_whitespace(raw):
    # case-insensitive + stripped
    assert is_product_active({"status": raw}) is False


def test_active_status_string_is_active():
    assert is_product_active({"status": "ACTIVE"}) is True
    assert is_product_active({"productStatus": "PUBLISHED"}) is True


@pytest.mark.parametrize("field,value,expected", [
    ("archived", True, False),
    ("archived", False, True),
    ("isArchived", True, False),
    ("isArchived", False, True),
    ("active", False, False),
    ("active", True, True),
    ("isActive", False, False),
    ("isActive", True, True),
])
def test_boolean_flags_in_isolation(field, value, expected):
    assert is_product_active({field: value}) is expected


def test_absent_fields_default_active():
    assert is_product_active({}) is True
    assert is_product_active({"title": "Cup", "price": 100}) is True


def test_mixed_signal_one_inactive_wins():
    # active flag True but status archived -> inactive (any inactive signal wins)
    assert is_product_active({"active": True, "status": "ARCHIVED"}) is False
    assert is_product_active({"isActive": True, "archived": True}) is False


def test_truthy_nonbool_flag_does_not_trigger():
    # Only `is True` / `is False` are decisive; truthy strings are ignored.
    assert is_product_active({"archived": "yes"}) is True
    assert is_product_active({"active": 1}) is True  # 1 is not False


# ─── Property-based tests (Tasks 1.2 / 1.3) ───────────────────────────────────

if HAS_HYPOTHESIS:

    _status_strategy = st.one_of(
        st.none(),
        st.sampled_from(sorted(ARCHIVED_STATUSES)),
        st.sampled_from([s.lower() for s in ARCHIVED_STATUSES]),
        st.sampled_from(["ACTIVE", "PUBLISHED", "ON_SALE", "DRAFT"]),
        st.text(max_size=12),
    )
    _flag_strategy = st.one_of(st.none(), st.booleans())

    @settings(max_examples=200)
    @given(
        status=_status_strategy,
        product_status=_status_strategy,
        archived=_flag_strategy,
        is_archived=_flag_strategy,
        active=_flag_strategy,
        is_active=_flag_strategy,
    )
    def test_property_active_filter_matches_spec(
        status, product_status, archived, is_archived, active, is_active
    ):
        """Property 1: returns False iff any inactive signal is present."""
        p = {}
        if status is not None:
            p["status"] = status
        if product_status is not None:
            p["productStatus"] = product_status
        if archived is not None:
            p["archived"] = archived
        if is_archived is not None:
            p["isArchived"] = is_archived
        if active is not None:
            p["active"] = active
        if is_active is not None:
            p["isActive"] = is_active

        def inactive_signal(prod):
            for f in ("status", "productStatus"):
                v = prod.get(f)
                if isinstance(v, str) and v.strip().upper() in ARCHIVED_STATUSES:
                    return True
            if prod.get("archived") is True:
                return True
            if prod.get("isArchived") is True:
                return True
            if prod.get("active") is False:
                return True
            if prod.get("isActive") is False:
                return True
            return False

        expected = not inactive_signal(p)
        assert is_product_active(p) is expected

    @settings(max_examples=200)
    @given(
        extra=st.dictionaries(
            keys=st.sampled_from(["title", "name", "price", "id", "skuList", "rating"]),
            values=st.one_of(st.integers(), st.text(max_size=10)),
        )
    )
    def test_property_fail_open_default(extra):
        """Property 2: no inspected status/flag field present -> active (True)."""
        # ensure none of the inspected keys are present
        for k in ("status", "productStatus", "archived", "isArchived", "active", "isActive"):
            extra.pop(k, None)
        assert is_product_active(extra) is True
