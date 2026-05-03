"""Tests for `app/scheduler.py` — therapy product wrapper around the
seed-side `noctusai_lib.api.scheduler` primitive.

Covers `configure()` (env-flag gate + registration) and `audio_retention_job`
(sweep invocation + error swallow). The primitive itself is tested
upstream at `seed/lib/backend/tests/test_scheduler.py`.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from noctusai_lib.api import scheduler as seed_scheduler


@pytest.fixture(autouse=True)
def _reset_seed_scheduler():
    seed_scheduler.reset_for_testing()
    yield
    seed_scheduler.reset_for_testing()


class TestConfigure:
    def test_configure_skipped_when_flag_disabled(self):
        from app import scheduler as therapy_scheduler

        with patch.object(therapy_scheduler.settings, "therapy_scheduler_enabled", False):
            therapy_scheduler.configure()

        assert seed_scheduler.scheduler.get_jobs() == []

    def test_configure_registers_audio_retention(self):
        from app import scheduler as therapy_scheduler

        with patch.object(therapy_scheduler.settings, "therapy_scheduler_enabled", True), \
             patch.object(therapy_scheduler.settings, "therapy_audio_retention_sweep_interval_hours", 12):
            therapy_scheduler.configure()

        job = seed_scheduler.scheduler.get_job("therapy_audio_retention")
        assert job is not None


class TestAudioRetentionJob:
    @pytest.mark.asyncio
    async def test_invokes_sweep(self):
        from app import scheduler as therapy_scheduler

        admin_client = MagicMock()
        sweep = MagicMock(return_value={"expired": 3, "deleted": 3})

        with patch.object(therapy_scheduler, "get_admin_client", return_value=admin_client), \
             patch.object(therapy_scheduler, "run_retention_sweep", sweep):
            await therapy_scheduler.audio_retention_job()

        sweep.assert_called_once_with(admin_client)

    @pytest.mark.asyncio
    async def test_swallows_sweep_errors_with_logging(self, caplog):
        from app import scheduler as therapy_scheduler

        sweep = MagicMock(side_effect=RuntimeError("simulated DB outage"))

        with patch.object(therapy_scheduler, "get_admin_client", return_value=MagicMock()), \
             patch.object(therapy_scheduler, "run_retention_sweep", sweep):
            with caplog.at_level("ERROR", logger=therapy_scheduler.logger.name):
                await therapy_scheduler.audio_retention_job()

        assert any(
            "Therapy audio-retention sweep failed" in r.message
            for r in caplog.records
        ), caplog.records


class TestReExports:
    def test_start_scheduler_re_export(self):
        from app import scheduler as therapy_scheduler

        # Same callable as the seed-side primitive.
        assert therapy_scheduler.start_scheduler is seed_scheduler.start_scheduler
        assert therapy_scheduler.stop_scheduler is seed_scheduler.stop_scheduler
