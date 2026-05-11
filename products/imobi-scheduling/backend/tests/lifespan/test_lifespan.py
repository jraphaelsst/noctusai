"""Tests for `app.lifespan` — FastAPI startup / shutdown hooks.

Two paths verified:
  - **admin_client absent** (early-dev / no service-role key) → loud WARN,
    no conversation module configured, no worker started.
  - **admin_client present** → `configure_conversation_module` called,
    `start_worker` invoked.

Shutdown is best-effort — tolerates "no worker was started" by short-
circuiting in `stop_worker`.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def reset_conversation_module():
    from app.services import conversation

    conversation._reset_for_tests()
    yield
    conversation._reset_for_tests()


@pytest.mark.asyncio
async def test_on_startup_skips_when_no_admin_client(caplog):
    """When `get_admin_client()` returns None, lifespan logs a WARN
    and short-circuits — no conversation module, no worker."""
    from app import lifespan as ls

    with patch.object(ls, "get_admin_client", return_value=None), \
         patch.object(ls, "configure_conversation_module") as mock_config, \
         patch.object(ls, "start_worker") as mock_start:
        with caplog.at_level("WARNING"):
            await ls.on_startup()

    mock_config.assert_not_called()
    mock_start.assert_not_called()
    warnings = [
        r.message for r in caplog.records
        if r.levelname == "WARNING" and "no admin client" in r.message
    ]
    assert warnings, "Expected a WARNING when admin_client is None"


@pytest.mark.asyncio
async def test_on_startup_configures_module_and_starts_worker():
    from app import lifespan as ls

    admin = MagicMock(name="admin_client")
    with patch.object(ls, "get_admin_client", return_value=admin), \
         patch.object(ls, "configure_conversation_module") as mock_config, \
         patch.object(ls, "start_worker") as mock_start:
        await ls.on_startup()

    mock_config.assert_called_once()
    kwargs = mock_config.call_args.kwargs
    assert kwargs["admin_client"] is admin
    assert "org_id" in kwargs
    mock_start.assert_called_once()


@pytest.mark.asyncio
async def test_on_shutdown_calls_stop_worker():
    from app import lifespan as ls

    with patch.object(ls, "stop_worker") as mock_stop:
        await ls.on_shutdown()

    mock_stop.assert_called_once()


def test_lifespan_wired_into_main_app():
    """The FastAPI `app` exposes the lifespan hooks via the seed factory.
    Sanity check that `main.py` did wire them — drift here would silently
    break Phase 6."""
    from app import main as main_mod
    from app.lifespan import on_shutdown, on_startup

    # The FastAPI app does NOT directly expose the original callables —
    # they're closed over by the seed's lifespan context manager. Verify
    # at import-binding level: `main` references the right names.
    assert main_mod.on_startup is on_startup
    assert main_mod.on_shutdown is on_shutdown
