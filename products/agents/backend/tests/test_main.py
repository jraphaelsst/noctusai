"""Tests for ``app.main``'s contract §E.11 startup + health wiring:
"Every slot is swept once at startup" and "Any failure quarantines K ...
`/api/health` reports degraded" (the seed's supported extension point for
that signal is ``/_health`` — see ``app/main.py``'s module docstring for
why ``/api/health`` itself has no hook seam).

The ``agents_client`` fixture (``tests/routers/conftest.py``) already
enters the app's lifespan on every test, so `on_startup()`'s slot-pool
sweep has already run by the time a test body executes — these tests
assert on its OBSERVABLE OUTCOME (the process-wide `SlotPool` singleton's
own state), never on a mock of our own code.
"""
from __future__ import annotations

from app.config import settings
from app.runtime.slots import get_slot_pool
from tests.routers.conftest import agents_client  # noqa: F401 — re-exported fixture


class TestStartupSweepsTheSlotPool:
    def test_sweep_ran_and_left_the_pool_healthy(self, agents_client):
        pool = get_slot_pool(settings)
        health = pool.health()
        assert health["total"] == settings.julia_cli_slots
        assert health["quarantined"] == []


class TestSlotPoolHealthDegradesOnQuarantine:
    def test_a_quarantined_slot_degrades_health_endpoint(self, agents_client):
        pool = get_slot_pool(settings)

        # Force a quarantine on the REAL, live singleton's own free-list —
        # the same data structure `_BaseSlotPool._release` /
        # `sweep_all_on_startup` mutate on a genuine failure — so this
        # exercises the health hook against real pool state, not a stub.
        pool._free.remove(0)
        pool._quarantined.add(0)
        try:
            resp = agents_client.raw().get("/_health")
            assert resp.status_code == 503
            body = resp.json()
            assert body["ok"] is False
            check = next(c for c in body["checks"] if c["name"] == "_slot_pool_health")
            assert check["ok"] is False
            assert "0" in check["error"]
        finally:
            pool._quarantined.discard(0)
            pool._free.append(0)

    def test_no_quarantine_reports_healthy(self, agents_client):
        resp = agents_client.raw().get("/_health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        check = next(c for c in body["checks"] if c["name"] == "_slot_pool_health")
        assert check == {"name": "_slot_pool_health", "ok": True, "error": None}
