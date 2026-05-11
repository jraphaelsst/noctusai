"""Tests for the seed `scheduler` standard router.

Scope: GET `/api/scheduler/jobs` (list) and GET `/api/scheduler/jobs/{job_id}`
(detail) — happy path, empty list, auth boundary, job-not-found.

Test-data strategy: seed REAL APScheduler jobs via
``noctusai_lib.api.scheduler.register(...)`` (the same API products use)
rather than monkey-patching `get_jobs()` — per the
"no-monkey-patching-of-our-own-code" rule. `reset_for_testing()` clears
state between cases so they don't bleed.

Auth-boundary tests use an `AsyncMock` on `deps.get_current_user` (the
auth seam). That's the external service boundary — patching there is
fine; patching the router's own logic would not be.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient

from noctusai_lib.api import scheduler as scheduler_module
from noctusai_seed.scheduler_router import create_scheduler_router


@pytest.fixture(autouse=True)
def reset_scheduler():
    """Clear scheduler state before AND after each test so a leaked job
    from one case cannot poison another. The seed lib exposes this exact
    helper for the use case."""
    scheduler_module.reset_for_testing()
    yield
    scheduler_module.reset_for_testing()


def _build_app(deps):
    """Mount the scheduler router on a fresh FastAPI app."""
    app = FastAPI()
    router: APIRouter = create_scheduler_router(deps)
    app.include_router(router)
    return app


def _client_with_deps(deps):
    return TestClient(_build_app(deps))


def _authed_deps(fake_deps):
    """Wire `get_current_user` to succeed (returns a fake user)."""
    user = MagicMock()
    user.id = "user-1"
    fake_deps.get_current_user = AsyncMock(return_value=(user, "tok"))
    return fake_deps


async def _noop_job():  # pragma: no cover — registered, never invoked in tests
    return None


class TestListJobsEndpoint:
    def test_empty_list_when_no_jobs_registered(self, fake_deps):
        deps = _authed_deps(fake_deps)
        client = _client_with_deps(deps)

        resp = client.get(
            "/api/scheduler/jobs",
            headers={"Authorization": "Bearer t"},
        )

        # Status MUST be asserted alongside body per status-code-assertion-rule.
        assert resp.status_code == 200
        assert resp.json() == []

    def test_happy_path_returns_registered_jobs(self, fake_deps):
        # Seed real jobs via the public API — exercises the same path
        # products use.
        scheduler_module.register("daily_digest", _noop_job, cron="0 6 * * *")
        scheduler_module.register("hourly_sweep", _noop_job, hours=1)

        deps = _authed_deps(fake_deps)
        client = _client_with_deps(deps)

        resp = client.get(
            "/api/scheduler/jobs",
            headers={"Authorization": "Bearer t"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 2

        by_id = {j["id"]: j for j in body}
        assert "daily_digest" in by_id
        assert "hourly_sweep" in by_id

        # Cron trigger: kind + non-wildcard fields present.
        cron_job = by_id["daily_digest"]
        assert cron_job["trigger_kind"] == "cron"
        assert cron_job["trigger_args"].get("hour") == "6"
        assert cron_job["trigger_args"].get("minute") == "0"

        # Interval trigger: kind + total seconds present.
        interval_job = by_id["hourly_sweep"]
        assert interval_job["trigger_kind"] == "interval"
        assert interval_job["trigger_args"].get("seconds") == 3600

    def test_next_run_time_field_present_and_nullable(self, fake_deps):
        """APScheduler leaves `next_run_time` as None until the scheduler
        is started (start requires a running event loop, which the
        TestClient doesn't bring). Pre-start, the DTO emits None for
        that field — the contract is `next_run_time: datetime | None`."""
        scheduler_module.register("ticker", _noop_job, minutes=5)

        deps = _authed_deps(fake_deps)
        client = _client_with_deps(deps)

        resp = client.get(
            "/api/scheduler/jobs",
            headers={"Authorization": "Bearer t"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["id"] == "ticker"
        # Pre-start, APScheduler populates next_run_time as None — the
        # DTO surface must accept and emit that.
        assert "next_run_time" in body[0]
        assert body[0]["next_run_time"] is None


class TestGetJobEndpoint:
    def test_happy_path_returns_one_job(self, fake_deps):
        scheduler_module.register("daily_digest", _noop_job, cron="0 6 * * *")

        deps = _authed_deps(fake_deps)
        client = _client_with_deps(deps)

        resp = client.get(
            "/api/scheduler/jobs/daily_digest",
            headers={"Authorization": "Bearer t"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "daily_digest"
        assert body["trigger_kind"] == "cron"
        assert body["trigger_args"].get("hour") == "6"

    def test_job_not_found_returns_404(self, fake_deps):
        # No jobs registered. Asking for an arbitrary id must 404.
        deps = _authed_deps(fake_deps)
        client = _client_with_deps(deps)

        resp = client.get(
            "/api/scheduler/jobs/does-not-exist",
            headers={"Authorization": "Bearer t"},
        )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Job nao encontrado"

    def test_other_registered_job_does_not_match(self, fake_deps):
        scheduler_module.register("real_job", _noop_job, hours=1)

        deps = _authed_deps(fake_deps)
        client = _client_with_deps(deps)

        resp = client.get(
            "/api/scheduler/jobs/some_other_id",
            headers={"Authorization": "Bearer t"},
        )

        assert resp.status_code == 404


class TestAuthBoundary:
    """Auth gate sits at `deps.get_current_user`. Failures there bubble
    up as `HTTPException(401)` — the router must surface them, not
    swallow them."""

    def test_list_jobs_unauth_returns_401(self, fake_deps):
        # Simulate the real `get_current_user` behavior on missing token
        # by raising 401 from the AsyncMock.
        fake_deps.get_current_user = AsyncMock(
            side_effect=HTTPException(status_code=401, detail="Token ausente")
        )

        # Even with jobs registered, the auth gate fires first.
        scheduler_module.register("daily_digest", _noop_job, cron="0 6 * * *")

        client = _client_with_deps(fake_deps)
        resp = client.get("/api/scheduler/jobs")

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Token ausente"

    def test_get_job_unauth_returns_401(self, fake_deps):
        fake_deps.get_current_user = AsyncMock(
            side_effect=HTTPException(status_code=401, detail="Token invalido")
        )

        # Job exists, but auth fires before lookup — caller sees 401, not 200.
        scheduler_module.register("daily_digest", _noop_job, cron="0 6 * * *")

        client = _client_with_deps(fake_deps)
        resp = client.get(
            "/api/scheduler/jobs/daily_digest",
            headers={"Authorization": "Bearer bad"},
        )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Token invalido"

    def test_get_job_unauth_fires_before_404(self, fake_deps):
        """Auth must fire BEFORE the 404 lookup — otherwise we leak
        existence info to unauth'd callers."""
        fake_deps.get_current_user = AsyncMock(
            side_effect=HTTPException(status_code=401, detail="Token ausente")
        )

        # No jobs registered — authed caller would get 404. Unauth'd MUST get 401.
        client = _client_with_deps(fake_deps)
        resp = client.get("/api/scheduler/jobs/anything")

        assert resp.status_code == 401


class TestRegistryWiring:
    """Confirm the standard-router registry resolves `"scheduler"` to
    this factory. This is the integration boundary between the registry
    and the router file."""

    def test_scheduler_registered_in_standard_routers(self):
        from noctusai_seed.routers import _STANDARD_ROUTERS

        assert "scheduler" in _STANDARD_ROUTERS

    def test_build_standard_routers_emits_scheduler(self, fake_deps, fake_settings, product_name, version):
        from noctusai_seed.routers import build_standard_routers

        result = build_standard_routers(
            fake_deps, fake_settings, product_name=product_name, version=version,
            names=["scheduler"],
        )

        assert len(result) == 1
        paths = {route.path for route in result[0].routes}
        assert "/api/scheduler/jobs" in paths
        assert "/api/scheduler/jobs/{job_id}" in paths
