"""Tests for Core's background scheduler.

Covers the webhook_retention_sweep_job + start/stop semantics.
Pattern mirrors `products/personal-finance/backend/tests/services/test_scheduler.py`.
"""
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_webhook_retention_sweep_job_no_expired_rows():
    """Job completes gracefully when `run_retention_sweep` returns 0 purged."""
    db = MagicMock()

    with (
        patch("app.scheduler.get_admin_client", return_value=db),
        patch("app.scheduler.run_retention_sweep", return_value={"purged": 0}) as mock_sweep,
    ):
        from app.scheduler import webhook_retention_sweep_job
        await webhook_retention_sweep_job()

    mock_sweep.assert_called_once_with(db)


@pytest.mark.asyncio
async def test_webhook_retention_sweep_job_logs_purge_count():
    """Job logs purged count when non-zero."""
    db = MagicMock()

    with (
        patch("app.scheduler.get_admin_client", return_value=db),
        patch("app.scheduler.run_retention_sweep", return_value={"purged": 42}) as mock_sweep,
        patch("app.scheduler.logger") as mock_logger,
    ):
        from app.scheduler import webhook_retention_sweep_job
        await webhook_retention_sweep_job()

    mock_sweep.assert_called_once_with(db)
    mock_logger.info.assert_called_once()
    call_args = mock_logger.info.call_args[0]
    assert "42" in str(call_args) or 42 in call_args


@pytest.mark.asyncio
async def test_webhook_retention_sweep_job_swallows_errors():
    """Job does not raise if the sweep fails — errors logged, scheduler continues."""
    db = MagicMock()

    with (
        patch("app.scheduler.get_admin_client", return_value=db),
        patch("app.scheduler.run_retention_sweep", side_effect=RuntimeError("DB down")),
        patch("app.scheduler.logger") as mock_logger,
    ):
        from app.scheduler import webhook_retention_sweep_job
        # Must not raise
        await webhook_retention_sweep_job()

    mock_logger.error.assert_called_once()
    assert "DB down" in str(mock_logger.error.call_args)


@pytest.mark.asyncio
async def test_start_scheduler_registers_webhook_job():
    """start_scheduler adds the retention job with a cron trigger."""
    from app import scheduler as scheduler_module

    if scheduler_module.scheduler.running:
        scheduler_module.scheduler.shutdown(wait=False)

    try:
        scheduler_module.start_scheduler()
        job = scheduler_module.scheduler.get_job("core_webhook_retention_sweep")
        assert job is not None
        assert job.id == "core_webhook_retention_sweep"
    finally:
        scheduler_module.stop_scheduler()


@pytest.mark.asyncio
async def test_start_scheduler_is_idempotent():
    """Calling start_scheduler twice does not raise."""
    from app import scheduler as scheduler_module

    if scheduler_module.scheduler.running:
        scheduler_module.scheduler.shutdown(wait=False)

    try:
        scheduler_module.start_scheduler()
        assert scheduler_module.scheduler.running
        scheduler_module.start_scheduler()
        assert scheduler_module.scheduler.running
    finally:
        scheduler_module.stop_scheduler()


def test_stop_scheduler_is_safe_when_not_running():
    """stop_scheduler does not raise when called on an inactive scheduler."""
    from app import scheduler as scheduler_module

    if scheduler_module.scheduler.running:
        scheduler_module.scheduler.shutdown(wait=False)

    scheduler_module.stop_scheduler()
    assert not scheduler_module.scheduler.running
