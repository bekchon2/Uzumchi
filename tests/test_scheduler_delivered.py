"""
Delivered-date formatting: the scheduler must format timestamps via
utils.helpers.format_date (DD.MM.YYYY) and must never reference `ms_to_date`.
"""
import inspect

import services.scheduler as scheduler
from utils.helpers import format_date


def test_format_date_basic():
    # 1700000000000 ms == 2023-11-15 in Asia/Tashkent
    assert format_date(1700000000000) == "15.11.2023"


def test_format_date_zero_does_not_raise():
    # Guard: a zero/epoch timestamp must format without raising.
    result = format_date(0)
    assert isinstance(result, str) and result


def test_scheduler_imports_format_date():
    # format_date must be importable/usable inside the scheduler module.
    assert hasattr(scheduler, "format_date")
    assert scheduler.format_date is format_date


def test_scheduler_never_references_ms_to_date():
    src = inspect.getsource(scheduler)
    assert "ms_to_date" not in src, "ms_to_date must not be introduced anywhere"


def test_delivered_detail_renders_date_via_t():
    from locales.i18n import t
    out = t(
        "sched_delivered_detail", "ru",
        name="Item", sku="SKU", price=1000,
        commission=100, profit=700, date=format_date(1700000000000),
    )
    assert "15.11.2023" in out
