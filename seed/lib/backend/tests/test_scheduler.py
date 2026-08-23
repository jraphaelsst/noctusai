"""Tests for `noctusai_lib.api.scheduler` primitive.

The primitive itself is module-level state (singleton AsyncIOScheduler).
`reset_for_testing()` is the test-cycle reset — used by both these tests
and the per-product wrappers' conftests.
"""
from __future__ import annotations

import os
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

    def test_start_logs_registered_jobs(self, monkeypatch):
        """When the scheduler starts, it logs the job names so operators
        can confirm what's wired.

        Needs `NOCTUS_SCHEDULERS_ENABLED` since 2026-08-22: `start_scheduler`
        refuses to start an unauthorised process, and this test exercises the
        STARTED path.
        """
        async def _job():
            return None

        monkeypatch.setenv(sched.SCHEDULERS_ENABLED_ENV, "1")
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


class TestSchedulersEnabledGate:
    """Pins the 2026-08-22 incident fix.

    A social-wiring backend left running on a developer laptop against the
    production `.env` woke during a macOS DarkWake, fired the nightly Vista
    sync, and wrote 50 rows to the live catalog. All fourteen registered
    jobs were live on that process — Meta ads, OLX drains, e-mail sends,
    YouTube snapshots — every one writing to production.

    The gate is an env marker set ONLY by the prod compose, never by
    `.env`, because `.env` is the file that gets copied to laptops.
    """

    def test_start_is_refused_without_the_marker(self, monkeypatch):
        async def _job():
            return None

        monkeypatch.delenv(sched.SCHEDULERS_ENABLED_ENV, raising=False)
        sched.register("nightly", _job, cron="5 0 * * *")

        sched.start_scheduler()

        assert not sched.scheduler.running

    def test_jobs_still_REGISTER_when_refused(self, monkeypatch):
        """Registration is untouched — only firing is gated.

        A local run must still get the real app and the real wiring; the
        difference is that nothing writes.
        """
        async def _job():
            return None

        monkeypatch.delenv(sched.SCHEDULERS_ENABLED_ENV, raising=False)
        sched.register("nightly", _job, cron="5 0 * * *")

        sched.start_scheduler()

        assert len(sched.scheduler.get_jobs()) == 1

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
    def test_marker_accepts_the_usual_truthy_spellings(self, monkeypatch, value):
        monkeypatch.setenv(sched.SCHEDULERS_ENABLED_ENV, value)
        assert sched.schedulers_enabled() is True

    @pytest.mark.parametrize("value", ["", "0", "false", "no", "off", " "])
    def test_marker_rejects_everything_else(self, monkeypatch, value):
        monkeypatch.setenv(sched.SCHEDULERS_ENABLED_ENV, value)
        assert sched.schedulers_enabled() is False

    def test_prod_env_markers_alone_do_NOT_authorise(self, monkeypatch):
        """The load-bearing case: a laptop holding the production `.env`.

        `is_deploy_context()` is True here — APP_ENV and PRODUCT_URL_* are
        exactly what a copied prod `.env` carries. If the gate keyed off
        that, the incident would repeat verbatim.
        """
        monkeypatch.delenv(sched.SCHEDULERS_ENABLED_ENV, raising=False)
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("PRODUCT_URL_SOCIAL_WIRING", "https://x.example.com")

        from noctusai_lib.config.deploy_config import is_deploy_context

        assert is_deploy_context() is True, "fixture no longer models a prod env"
        assert sched.schedulers_enabled() is False

        async def _job():
            return None

        sched.register("nightly", _job, cron="5 0 * * *")
        sched.start_scheduler()
        assert not sched.scheduler.running

    def test_marker_present_starts_normally(self, monkeypatch):
        async def _job():
            return None

        monkeypatch.setenv(sched.SCHEDULERS_ENABLED_ENV, "1")
        sched.register("nightly", _job, cron="5 0 * * *")

        # `AsyncIOScheduler.start()` binds the running loop, and there is
        # none in a sync test — patch it, exactly as the pre-existing
        # start-path test does. What is under test is that the gate LETS
        # the call through, not APScheduler's own startup.
        with patch.object(sched.scheduler, "start") as real_start:
            sched.start_scheduler()

        real_start.assert_called_once()

    def test_missing_marker_IN_A_DEPLOY_logs_at_ERROR(self, monkeypatch, caplog):
        """Prod silently running zero jobs is worse than the original bug.

        A laptop gets INFO; a deploy context missing the marker gets ERROR,
        because that means the compose lost the line.
        """
        monkeypatch.delenv(sched.SCHEDULERS_ENABLED_ENV, raising=False)
        monkeypatch.setenv("APP_ENV", "production")

        with caplog.at_level("INFO"):
            sched.start_scheduler()

        assert any(r.levelname == "ERROR" for r in caplog.records), (
            "a deployed container with no scheduler marker must be loud"
        )

    def test_missing_marker_OUTSIDE_a_deploy_is_only_INFO(self, monkeypatch, caplog):
        """A developer laptop behaving correctly must not look broken."""
        monkeypatch.delenv(sched.SCHEDULERS_ENABLED_ENV, raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)
        for key in list(os.environ):
            if key.startswith("PRODUCT_URL_"):
                monkeypatch.delenv(key, raising=False)

        with caplog.at_level("INFO"):
            sched.start_scheduler()

        assert not any(r.levelname == "ERROR" for r in caplog.records)
        assert any(r.levelname == "INFO" for r in caplog.records)
