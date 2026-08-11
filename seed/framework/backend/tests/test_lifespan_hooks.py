"""Regression tests: a product lifespan hook must NEVER abort the boot.

WHAT THIS PINS
--------------
`create_product_app(..., lifespan_startup=hook)` runs a product-supplied
side-effect hook (recover stuck rows, schedule pending jobs, start a
scheduler). Until 2026-08-10 an exception out of that hook propagated
through the FastAPI `lifespan` contextmanager, which uvicorn reports as::

    ERROR:    Application startup failed. Exiting.

…and the process dies. erp-imobiliario spent 13 days down on the dev fleet
because ONE `httpx.ConnectError` (a PostgREST TLS reset) escaped
`recover_stuck_processando`. Prod, on the same code with a healthy network,
served fine the whole time — which is exactly why this class of bug hides:
it only ever fires where the upstream is flaky.

The rule this file enforces: **a startup hook is a side effect, not a
precondition for serving.** The API comes up regardless; the failure is
loud (ERROR + traceback) and NAMED (`/api/health.startup_hook_error`), so
this is a reported degradation, not a silent fallback.

→ `KB § PATTERNS/backend/startup-hook-must-not-be-fatal.md`
"""
from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def minimal_settings():
    """Same shape `test_health.py` uses — no DB / vendor wiring needed."""

    class _S:
        cors_origins = "http://localhost:3000"
        cors_origins_list = ["http://localhost:3000"]
        debug = True
        is_production = False
        sentry_dsn = None
        product_slug = "test"
        supabase_url = "http://localhost:54321"
        supabase_anon_key = "anon"
        supabase_service_role_key = "service"
        consent_gating = False
        llm_usage_tracking = False
        redis_url = None

    return _S()


def _app(minimal_settings, **kwargs):
    from noctusai_seed import create_product_app

    return create_product_app(
        name="Test",
        schema="test",
        settings=minimal_settings,
        routers=None,
        version="9.9.9",
        standard_routers=["health"],
        **kwargs,
    )


# ---------------------------------------------------------------------------
# The regression itself
# ---------------------------------------------------------------------------


def test_raising_sync_startup_hook_does_not_abort_boot(minimal_settings):
    """THE bug. A sync hook that raises used to kill the process."""
    calls = []

    def recover_stuck_processando():
        calls.append("ran")
        raise ConnectionError("[SSL: UNEXPECTED_EOF_WHILE_READING] EOF in violation of protocol")

    app = _app(minimal_settings, lifespan_startup=recover_stuck_processando)

    # Entering the TestClient context runs the lifespan. Before the fix this
    # raised ConnectionError right here — the app never served a request.
    with TestClient(app) as client:
        assert calls == ["ran"], "the hook must still be ATTEMPTED, not skipped"
        assert client.get("/api/health").status_code == 200


def test_raising_async_startup_hook_does_not_abort_boot(minimal_settings):
    """Same contract on the async branch of `_is_coroutine`."""

    async def start_scheduler():
        raise RuntimeError("redis refused the connection")

    with TestClient(_app(minimal_settings, lifespan_startup=start_scheduler)) as client:
        assert client.get("/api/health").status_code == 200


def test_failure_is_reported_on_health_not_swallowed(minimal_settings):
    """No silent fallback: the exception is named on `/api/health`.

    This is the assertion that separates "degrades honestly" from "hides the
    problem". Delete the `startup_hook_error` field and this test fails.
    """

    def recover():
        raise ConnectionError("PostgREST unreachable")

    with TestClient(_app(minimal_settings, lifespan_startup=recover)) as client:
        body = client.get("/api/health").json()

    assert body["status"] == "ok", "the API IS serving — degradation is a field, not a status"
    assert body["startup_hook_error"] == "ConnectionError: PostgREST unreachable"


def test_clean_boot_reports_null(minimal_settings):
    """The field must be present-and-null on a healthy boot, so a consumer
    can distinguish "no failure" from "old seed that lacks the field"."""

    def recover():
        return None

    with TestClient(_app(minimal_settings, lifespan_startup=recover)) as client:
        body = client.get("/api/health").json()

    assert "startup_hook_error" in body
    assert body["startup_hook_error"] is None


def test_no_startup_hook_at_all_reports_null(minimal_settings):
    with TestClient(_app(minimal_settings)) as client:
        assert client.get("/api/health").json()["startup_hook_error"] is None


def test_failure_is_logged_at_error_with_traceback(minimal_settings):
    """Loud, not quiet — `logger.exception` so the traceback reaches the
    container logs. A WARNING here would be too easy to scroll past.

    NOT pytest's `caplog`: the seed installs its own logging config, and
    `noctusai_seed` does not propagate to root, so `caplog.records` comes back
    EMPTY even while the ERROR is plainly printed. That reads as "nothing was
    logged" — a false negative in the one test whose whole job is proving the
    failure is loud. Attach the handler to the actual logger instead.
    """
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    def recover():
        raise ConnectionError("boom")

    seed_logger = logging.getLogger("noctusai_seed.app")
    handler = _Capture(level=logging.ERROR)
    seed_logger.addHandler(handler)
    try:
        with TestClient(_app(minimal_settings, lifespan_startup=recover)):
            pass
    finally:
        seed_logger.removeHandler(handler)

    errors = [r for r in records if r.levelno >= logging.ERROR]
    assert errors, "a failed startup hook must log at ERROR"
    assert errors[0].exc_info is not None, "must use logger.exception (traceback attached)"
    assert "recover" in errors[0].getMessage()


# ---------------------------------------------------------------------------
# Shutdown side — a failing shutdown hook must not leak the LLM pools
# ---------------------------------------------------------------------------


def test_raising_shutdown_hook_still_runs_framework_cleanup(minimal_settings, monkeypatch):
    """`shutdown_llm()` lives AFTER the product shutdown hook in the same
    `finally`. An exception from the hook used to skip it, leaking provider
    pools on every shutdown that had a flaky teardown."""
    import noctusai_seed.app as app_mod

    closed = []

    async def _fake_shutdown_llm():
        closed.append("llm")

    monkeypatch.setattr(app_mod, "shutdown_llm", _fake_shutdown_llm)

    def stop_scheduler():
        raise RuntimeError("scheduler already dead")

    with TestClient(_app(minimal_settings, lifespan_shutdown=stop_scheduler)):
        pass

    assert closed == ["llm"], "framework cleanup must run even when the product hook raises"
