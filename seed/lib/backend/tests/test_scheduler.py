"""Tests for `noctusai_lib.api.scheduler` primitive.

The primitive itself is module-level state (singleton AsyncIOScheduler).
`reset_for_testing()` is the test-cycle reset — used by both these tests
and the per-product wrappers' conftests.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from noctusai_lib.api import scheduler as sched


@pytest.fixture(autouse=True)
def _reset_each_test():
    sched.reset_for_testing()
    yield
    sched.reset_for_testing()


class TestRegister:
    def test_register_with_hours(self):
        async def _job():
            return None

        sched.register("hourly", _job, hours=24)
        jobs = sched.scheduler.get_jobs()
        assert len(jobs) == 1
        assert jobs[0].id == "hourly"

    def test_register_with_minutes(self):
        async def _job():
            return None

        sched.register("minutely", _job, minutes=15)
        assert sched.scheduler.get_job("minutely") is not None

    def test_register_with_seconds(self):
        async def _job():
            return None

        sched.register("second_loop", _job, seconds=30)
        assert sched.scheduler.get_job("second_loop") is not None

    def test_register_with_cron(self):
        """Cron trigger — exercises the personal-finance "daily at 06:00 SP"
        pattern that interval-only would miss."""
        async def _job():
            return None

        sched.register("daily_six_am", _job, cron="0 6 * * *")
        assert sched.scheduler.get_job("daily_six_am") is not None

    def test_register_passes_replace_existing_true(self):
        """add_job is invoked with replace_existing=True so re-registration
        is idempotent across hot-reload / re-import."""
        async def _job():
            return None

        with patch.object(sched.scheduler, "add_job") as mock_add:
            sched.register("dup", _job, hours=1)
        assert mock_add.call_args.kwargs.get("replace_existing") is True
        assert mock_add.call_args.kwargs.get("id") == "dup"

    def test_register_rejects_zero_triggers(self):
        async def _job():
            return None

        with pytest.raises(ValueError, match="exactly one of"):
            sched.register("noargs", _job)

    def test_register_rejects_multiple_intervals(self):
        async def _job():
            return None

        with pytest.raises(ValueError, match="exactly one of"):
            sched.register("multi", _job, hours=1, minutes=30)

    def test_register_rejects_interval_plus_cron(self):
        async def _job():
            return None

        with pytest.raises(ValueError, match="exactly one of"):
            sched.register("both", _job, hours=1, cron="0 * * * *")


class TestStartStop:
    """`scheduler.running` is a property without a setter on AsyncIOScheduler,
    so these tests swap the module-level `scheduler` with a MagicMock for
    those that need to simulate running state."""

    def test_start_is_idempotent_when_already_running(self):
        """Calling `start_scheduler()` on a running scheduler must not
        raise — the lifespan wiring may invoke it more than once during
        re-init."""
        fake = MagicMock()
        fake.running = True
        with patch.object(sched, "scheduler", fake):
            sched.start_scheduler()
        fake.start.assert_not_called()

    def test_start_logs_registered_jobs(self):
        """When the scheduler starts, it logs the job names so operators
        can confirm what's wired."""
        async def _job():
            return None

        sched.register("logged_job", _job, hours=1)
        with patch.object(sched.scheduler, "start"), \
             patch.object(sched, "logger") as mock_logger:
            sched.start_scheduler()
        assert mock_logger.info.called
        log_msg = str(mock_logger.info.call_args)
        assert "logged_job" in log_msg

    def test_stop_is_safe_when_not_running(self):
        # Should not raise.
        sched.stop_scheduler()

    def test_stop_calls_shutdown_when_running(self):
        fake = MagicMock()
        fake.running = True
        with patch.object(sched, "scheduler", fake):
            sched.stop_scheduler()
        fake.shutdown.assert_called_once_with(wait=False)


class TestResetForTesting:
    def test_reset_clears_jobs(self):
        async def _job():
            return None

        sched.register("temp", _job, hours=1)
        assert sched.scheduler.get_job("temp") is not None
        sched.reset_for_testing()
        assert sched.scheduler.get_job("temp") is None

    def test_reset_replaces_singleton(self):
        old = sched.scheduler
        sched.reset_for_testing()
        assert sched.scheduler is not old


class TestRegisterIdempotency:
    """Pins the 2026-08-20 fix.

    `replace_existing=True` is consulted by the JOBSTORE, and a stopped
    scheduler has none — `add_job` parks into `_pending_jobs` and flushes
    at `start()`. Every adopting product registers at import time, before
    `start_scheduler()`, so the stopped path is the only one they exercise.
    Before the fix two `configure()` calls scheduled the job twice, with no
    error anywhere.
    """

    def test_double_register_on_stopped_scheduler_keeps_one_job(self):
        async def _job():
            return None

        sched.register("nightly", _job, cron="5 0 * * *")
        sched.register("nightly", _job, cron="5 0 * * *")

        assert len(sched.scheduler.get_jobs()) == 1

    def test_many_registers_still_keep_one_job(self):
        async def _job():
            return None

        for _ in range(5):
            sched.register("nightly", _job, cron="5 0 * * *")

        assert len(sched.scheduler.get_jobs()) == 1

    def test_re_register_applies_the_NEW_trigger(self):
        """Replacement must mean replacement, not first-write-wins."""
        async def _job():
            return None

        sched.register("shifty", _job, cron="0 6 * * *")
        sched.register("shifty", _job, cron="5 0 * * *")

        job = sched.scheduler.get_job("shifty")
        fields = {f.name: str(f) for f in job.trigger.fields}
        assert (fields["hour"], fields["minute"]) == ("0", "5")

    def test_re_register_swaps_the_callable(self):
        async def _first():
            return None

        async def _second():
            return None

        sched.register("swap", _first, hours=1)
        sched.register("swap", _second, hours=1)

        assert sched.scheduler.get_job("swap").func is _second

    def test_registering_a_second_name_does_not_disturb_the_first(self):
        async def _job():
            return None

        sched.register("alpha", _job, hours=1)
        sched.register("beta", _job, hours=2)

        assert {j.id for j in sched.scheduler.get_jobs()} == {"alpha", "beta"}

    def test_invalid_register_does_not_unregister_the_incumbent(self):
        """The drop happens AFTER validation.

        Dropping first would let a malformed call silently leave the
        scheduler with no job at all — strictly worse than the duplicate
        bug it replaces.
        """
        async def _job():
            return None

        sched.register("keeper", _job, hours=1)

        with pytest.raises(ValueError):
            sched.register("keeper", _job, hours=1, minutes=30)

        assert sched.scheduler.get_job("keeper") is not None

    def test_drain_clears_pre_existing_duplicates(self):
        """A process that ran before this fix already holds duplicates.

        `remove_job` deletes only the FIRST match, so a single removal
        would leave the rest live. Simulated by adding duplicates through
        the raw APScheduler API, exactly as the old `register` did.
        """
        async def _job():
            return None

        for _ in range(3):
            sched.scheduler.add_job(
                _job, "interval", hours=1, id="dupes", replace_existing=True,
            )
        assert len(sched.scheduler.get_jobs()) == 3

        sched.register("dupes", _job, cron="5 0 * * *")

        assert len(sched.scheduler.get_jobs()) == 1
