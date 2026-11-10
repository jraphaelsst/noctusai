"""Call-count budget of the mailing loops (KB § PATTERNS/backend/polling-request-budget.md).

A fake Supabase client makes every call free, so a loop firing every 30 s on an empty queue is green on
correctness alone (2026-11-09 egress incident: ~2.6k `send_logs` reads / 22 h with nothing to send). These tests
COUNT the reads, and pin that nothing a user is waiting for is delayed by the backoff (the wake calls)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from noctusai_lib.primitives.ttl_cache import IdleGate
from noctusai_lib.testing import MockSupabaseClient

from app.modules.email_marketing import scheduler as sched
from app.modules.email_marketing import wake
from app.modules.email_marketing.services.send_service import SendService


class _Clock:
    t = 1000.0

    def __call__(self) -> float:
        return self.t


class _CountingDb(MockSupabaseClient):
    """`MockSupabaseClient` that counts `.table(name)` calls per table."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: dict[str, int] = {}

    def table(self, name: str):  # type: ignore[override]
        self.calls[name] = self.calls.get(name, 0) + 1
        return super().table(name)


@pytest.fixture(autouse=True)
def _reset_module_gates():
    """The module-level gates are process state: leave them due, as at boot, before and after every test."""
    wake.SEND_GATE.busy()
    wake.CAMPAIGNS_GATE.busy()
    yield
    wake.SEND_GATE.busy()
    wake.CAMPAIGNS_GATE.busy()


def _settings() -> MagicMock:
    s = MagicMock()
    s.resend_api_key = ""
    s.default_from_name = "Noctus"
    s.default_from_email = "noreply@noctus.ai"
    return s


def test_send_loop_on_an_empty_queue_reads_send_logs_once_per_5_min_not_every_30s(monkeypatch):
    db = _CountingDb()
    db.set_table_data("send_logs", [])
    clock = _Clock()
    gate = IdleGate(wake.SEND_FALLBACK_S, clock=clock)
    for _ in range(240):  # 2 h of 30 s ticks
        asyncio.run(sched.send_loop_job(db=db, gate=gate))
        clock.t += 30
    assert db.calls.get("send_logs", 0) <= 25  # was 240


def test_queueing_a_send_wakes_the_idle_send_loop_at_once():
    db = _CountingDb()
    db.set_table_data("campaigns", [{"id": "c1", "list_id": "l1"}])
    db.set_table_data("contact_list_members", [
        {"list_id": "l1", "contact_id": "ct1",
         "contacts": {"id": "ct1", "email": "a@test.com", "nome": "A", "empresa": "X", "status": "active", "email_optin": "not_required"}},
    ])
    db.set_table_data("send_logs", [])
    assert wake.SEND_GATE.due()  # a probe starts ...
    wake.SEND_GATE.idle()  # ... finds the queue empty
    assert not wake.SEND_GATE.due()
    SendService(db, _settings()).queue_campaign_sends("c1", "org-1")
    assert wake.SEND_GATE.due()  # the next tick sends: nobody waits up to the 5 min fallback


def test_scheduled_campaigns_probe_sleeps_until_the_next_scheduled_at_and_loses_no_time():
    db = _CountingDb()
    now = datetime.now(timezone.utc)
    db.set_table_data("campaigns", [
        {"id": "c1", "org_id": "o1", "status": "agendada", "scheduled_at": (now + timedelta(seconds=90)).isoformat(), "list_id": None},
    ])
    clock = _Clock()
    gate = IdleGate(wake.CAMPAIGNS_FALLBACK_S, clock=clock)
    sched._scheduled_campaigns_sync(db, gate)  # sees it is 90 s away
    assert not gate.due()
    reads = db.calls["campaigns"]
    for _ in range(2):  # two more 30 s ticks: still asleep, no read
        clock.t += 30
        assert not gate.due()
    assert db.calls["campaigns"] == reads
    clock.t += 31  # 91 s: due -> the probe runs on that very tick
    assert gate.due()


def test_scheduled_campaigns_with_nothing_scheduled_costs_one_read_per_10_min():
    db = _CountingDb()
    db.set_table_data("campaigns", [])
    clock = _Clock()
    gate = IdleGate(wake.CAMPAIGNS_FALLBACK_S, clock=clock)
    for _ in range(120):  # 2 h of 60 s ticks
        if gate.due():
            sched._scheduled_campaigns_sync(db, gate)
        clock.t += 60
    assert db.calls.get("campaigns", 0) <= 13  # was 120


def test_scheduled_campaigns_start_the_due_one_and_leave_the_future_one():
    db = _CountingDb()
    now = datetime.now(timezone.utc)
    db.set_table_data("campaigns", [
        {"id": "due", "org_id": "o1", "status": "agendada", "scheduled_at": (now - timedelta(minutes=1)).isoformat(), "list_id": None},
        {"id": "later", "org_id": "o1", "status": "agendada", "scheduled_at": (now + timedelta(hours=1)).isoformat(), "list_id": None},
    ])
    gate = IdleGate(wake.CAMPAIGNS_FALLBACK_S, clock=_Clock())
    assert gate.due()
    sched._scheduled_campaigns_sync(db, gate)
    status = {c["id"]: c["status"] for c in db.table("campaigns").select("*").execute().data}
    assert status == {"due": "enviando", "later": "agendada"}
    assert gate.due()  # after real work the next tick looks again


def test_a_failing_send_loop_backs_off_instead_of_hammering_every_tick():
    class _Down(_CountingDb):
        def table(self, name):  # type: ignore[override]
            self.calls[name] = self.calls.get(name, 0) + 1
            raise RuntimeError("HTTP 402 restricted")

    db = _Down()
    clock = _Clock()
    gate = IdleGate(wake.SEND_FALLBACK_S, clock=clock)
    for _ in range(240):  # 2 h of 30 s ticks against an outage
        asyncio.run(sched.send_loop_job(db=db, gate=gate))
        clock.t += 30
    assert db.calls["send_logs"] <= 30  # exponential 30s..300s: ~27 attempts; was 240 (every tick)
