"""Tests for `app/scheduler.py` — therapy backend scheduler.

Covers the generic `register(...)` surface, the env-flag gate, the
audio-retention job's error path, and the start/stop lifecycle. Does NOT
exercise the real audio-retention sweep against a real DB — that's the job
of `tests/services/test_audio_retention_service.py`.

The module-level `scheduler` is reset between tests so re-registrations
across the suite don't bleed.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler


@pytest.fixture(autouse=True)
def _reset_scheduler():
    """Replace the module-level scheduler with a fresh AsyncIOScheduler each test."""
    from app import scheduler as scheduler_module

    fresh = AsyncIOScheduler(timezone="America/Sao_Paulo")
    original = scheduler_module.scheduler
    scheduler_module.scheduler = fresh
    try:
        yield
    finally:
        if fresh.running:
            fresh.shutdown(wait=False)
        scheduler_module.scheduler = original


class TestRegister:
    """`register(...)` validates input and adds jobs to the module scheduler."""

    def test_register_with_hours(self):
        from app import scheduler as scheduler_module

        async def _job():
            return None

        scheduler_module.register("test_hours", _job, hours=24)
        jobs = scheduler_module.scheduler.get_jobs()
        assert len(jobs) == 1
        assert jobs[0].id == "test_hours"

    def test_register_with_minutes(self):
        from app import scheduler as scheduler_module

        async def _job():
            return None

        scheduler_module.register("test_minutes", _job, minutes=15)
        assert scheduler_module.scheduler.get_job("test_minutes") is not None

    def test_register_passes_replace_existing_to_apscheduler(self):
        """The `replace_existing=True` flag is passed to APScheduler so
        re-registration after a hot-reload or scheduler restart is idempotent.
        We assert the kwarg was forwarded rather than running the scheduler
        (APScheduler's `replace_existing` only takes effect once the scheduler
        is started — not at pre-start `add_job` time)."""
        from app import scheduler as scheduler_module

        async def _job():
            return None

        with patch.object(scheduler_module.scheduler, "add_job") as mock_add:
            scheduler_module.register("dup", _job, hours=1)

        assert mock_add.called
        assert mock_add.call_args.kwargs.get("replace_existing") is True
        assert mock_add.call_args.kwargs.get("id") == "dup"

    def test_register_rejects_zero_intervals(self):
        from app import scheduler as scheduler_module

        async def _job():
            return None

        with pytest.raises(ValueError, match="exactly one of hours/minutes/seconds"):
            scheduler_module.register("noargs", _job)

    def test_register_rejects_multiple_intervals(self):
        from app import scheduler as scheduler_module

        async def _job():
            return None

        with pytest.raises(ValueError, match="exactly one of hours/minutes/seconds"):
            scheduler_module.register("multiargs", _job, hours=1, minutes=30)


class TestStartScheduler:
    """`start_scheduler()` honors the env flag + registers the audio-retention job."""

    def test_start_skipped_when_flag_disabled(self):
        from app import scheduler as scheduler_module

        with patch.object(scheduler_module.settings, "therapy_scheduler_enabled", False):
            scheduler_module.start_scheduler()

        assert not scheduler_module.scheduler.running
        assert scheduler_module.scheduler.get_jobs() == []

    def test_start_registers_audio_retention_when_enabled(self):
        """When the env flag is on, `start_scheduler()` calls `register(...)`
        with the audio-retention job + the configured interval, then starts
        the underlying APScheduler. We assert via mock to avoid needing a
        running asyncio loop here (APScheduler.start() requires one)."""
        from app import scheduler as scheduler_module

        with patch.object(scheduler_module.settings, "therapy_scheduler_enabled", True), \
             patch.object(scheduler_module.settings, "therapy_audio_retention_sweep_interval_hours", 12), \
             patch.object(scheduler_module, "register") as mock_register, \
             patch.object(scheduler_module.scheduler, "start") as mock_start:
            scheduler_module.start_scheduler()

        mock_register.assert_called_once()
        args, kwargs = mock_register.call_args
        assert args[0] == "therapy_audio_retention"
        assert args[1] is scheduler_module.audio_retention_job
        assert kwargs == {"hours": 12}
        mock_start.assert_called_once()


class TestStopScheduler:
    def test_stop_is_safe_when_not_running(self):
        from app import scheduler as scheduler_module

        # Should not raise
        scheduler_module.stop_scheduler()


class TestAudioRetentionJob:
    """The wrapper job calls `run_retention_sweep` with the admin client."""

    @pytest.mark.asyncio
    async def test_audio_retention_job_invokes_sweep(self):
        from app import scheduler as scheduler_module

        admin_client = MagicMock()
        sweep = MagicMock(return_value={"expired": 3, "deleted": 3})

        with patch.object(scheduler_module, "get_admin_client", return_value=admin_client), \
             patch.object(scheduler_module, "run_retention_sweep", sweep):
            await scheduler_module.audio_retention_job()

        sweep.assert_called_once_with(admin_client)

    @pytest.mark.asyncio
    async def test_audio_retention_job_swallows_sweep_errors_with_logging(self, caplog):
        """Errors are logged at ERROR level — never raised — so a bad sweep
        doesn't crash the scheduler loop."""
        from app import scheduler as scheduler_module

        sweep = MagicMock(side_effect=RuntimeError("simulated DB outage"))

        with patch.object(scheduler_module, "get_admin_client", return_value=MagicMock()), \
             patch.object(scheduler_module, "run_retention_sweep", sweep):
            with caplog.at_level("ERROR", logger=scheduler_module.logger.name):
                await scheduler_module.audio_retention_job()

        assert any(
            "Therapy audio-retention sweep failed" in r.message
            for r in caplog.records
        ), caplog.records
