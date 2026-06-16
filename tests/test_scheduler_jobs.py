"""
Tests for scheduler job registration.

Feature: disable-legacy-scheduler-notifications

Property 1 (Bug Condition): Legacy Jobs Are Not Scheduled.
  Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7
Property 2 (Preservation): Requested Jobs And Scheduler Construction Unchanged.
  Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6

These tests build the scheduler with a lightweight stub bot and inspect the
returned scheduler's registered jobs WITHOUT calling ``scheduler.start()`` — so
no job ever executes and no notifications are dispatched.
"""
import pytest

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from services.scheduler import start_scheduler


# The seven legacy notification job ids that must NOT be registered (Bug Condition).
LEGACY_IDS = [
    "morning_reports",
    "storage_alerts",
    "delivered_check",
    "rating_check_morning",
    "rating_check_evening",
    "forecast_check",
    "returns_check",
]

# The two requested job ids that must remain registered (NOT Bug Condition).
REQUESTED_IDS = ["product_report_morning", "sale_check"]


class StubBot:
    """Minimal stand-in for the aiogram Bot.

    ``start_scheduler`` only stores the bot in each job's ``args`` and never
    calls it during registration, so a plain object suffices.
    """
    pass


@pytest.fixture()
def scheduler():
    return start_scheduler(StubBot())


# ─── Property 1: Bug Condition — legacy jobs are not scheduled ────────────────

@pytest.mark.parametrize("legacy_id", LEGACY_IDS)
def test_legacy_job_not_registered(scheduler, legacy_id):
    """Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7

    For every legacy job id, the fixed scheduler must NOT register the job.
    (FAILS on unfixed code where the seven add_job calls still exist.)
    """
    assert scheduler.get_job(legacy_id) is None


# ─── Property 2: Preservation — requested jobs / construction unchanged ───────

@pytest.mark.parametrize("requested_id", REQUESTED_IDS)
def test_requested_job_registered(scheduler, requested_id):
    """Validates: Requirements 3.1, 3.2

    The two requested jobs remain registered.
    """
    assert scheduler.get_job(requested_id) is not None


def test_scheduler_timezone_is_tashkent(scheduler):
    """Validates: Requirements 3.6 — scheduler built with Asia/Tashkent tz."""
    assert str(scheduler.timezone) == "Asia/Tashkent"


def test_start_scheduler_returns_asyncio_scheduler(scheduler):
    """Validates: Requirements 3.6 — return value is an AsyncIOScheduler."""
    assert isinstance(scheduler, AsyncIOScheduler)


# ─── Post-fix: exactly the two requested jobs are registered ──────────────────

def test_exactly_two_jobs_registered(scheduler):
    """Validates: Requirements 2.7, 3.1, 3.2

    After the fix, only the two requested jobs remain. (FAILS on unfixed code
    which registers nine jobs.)
    """
    jobs = scheduler.get_jobs()
    assert len(jobs) == 2
    assert {job.id for job in jobs} == {"product_report_morning", "sale_check"}
