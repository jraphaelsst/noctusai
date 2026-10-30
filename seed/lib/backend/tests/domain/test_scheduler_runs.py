"""`noctusai_lib.domain.scheduler_runs` — the Real ledger on the mock client."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from noctusai_lib.api.scheduler import JobRun, JobSpec
from noctusai_lib.domain.scheduler_runs import (
    ALERT_KIND,
    FakeRunLedger,
    SupabaseRunLedger,
    make_run_ledger,
    sanitize_error,
)
from noctusai_lib.testing import MockSupabaseClient

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
ADMIN = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OTHER_ADMIN = "dddddddd-dddd-dddd-dddd-dddddddddddd"


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _run(job="sweep", status="error", error="RuntimeError: boom", at=NOW) -> JobRun:
    return JobRun(job=job, started_at=at, finished_at=at + timedelta(seconds=2),
                  status=status, duration_ms=2000, error=error)


@pytest.fixture
def db():
    client = MockSupabaseClient()
    client.set_table_data("noctus_users", [
        {"id": ADMIN, "role": "admin"},
        {"id": OTHER_ADMIN, "role": "admin"},
        {"id": "u-1", "role": "user"},
    ])
    client.set_table_data("scheduler_runs", [])
    client.set_table_data("scheduler_jobs", [])
    client.set_table_data("notifications", [])
    return client


def _ledger(db, clock):
    return SupabaseRunLedger("social-wiring", lambda: db, clock=clock)


def test_an_ok_run_is_one_row_and_no_alert(db):
    _ledger(db, Clock(NOW)).record(_run(status="ok", error=None))
    [row] = db.table("scheduler_runs").inserted_payloads
    assert row["product"] == "social-wiring"
    assert row["status"] == "ok"
    assert row["alerted"] is False
    assert row["duration_ms"] == 2000
    assert db.table("notifications").inserted_payloads == []


def test_an_error_alerts_every_platform_admin_once(db):
    _ledger(db, Clock(NOW)).record(_run())
    notes = db.table("notifications").inserted_payloads
    assert sorted(n["user_id"] for n in notes) == [ADMIN, OTHER_ADMIN]
    assert all(n["type"] == "system" and n["metadata"]["tipo"] == ALERT_KIND for n in notes)
    assert notes[0]["metadata"]["job"] == "sweep"
    [row] = db.table("scheduler_runs").inserted_payloads
    assert row["alerted"] is True


def test_a_second_failure_within_six_hours_is_not_re_alerted(db):
    clock = Clock(NOW)
    ledger = _ledger(db, clock)
    ledger.record(_run())
    clock.now = NOW + timedelta(hours=2)
    ledger.record(_run(at=clock.now))
    assert len(db.table("notifications").inserted_payloads) == 2  # the first alert's two admins only
    rows = db.table("scheduler_runs").inserted_payloads
    assert [r["alerted"] for r in rows] == [True, False]


def test_after_the_window_it_alerts_again(db):
    clock = Clock(NOW)
    ledger = _ledger(db, clock)
    ledger.record(_run())
    clock.now = NOW + timedelta(hours=7)
    ledger.record(_run(at=clock.now))
    assert len(db.table("notifications").inserted_payloads) == 4


def test_a_different_job_has_its_own_window(db):
    ledger = _ledger(db, Clock(NOW))
    ledger.record(_run(job="a"))
    ledger.record(_run(job="b"))
    assert len(db.table("notifications").inserted_payloads) == 4


def test_a_failed_notification_still_writes_the_run(db, caplog):
    class NoNotifications:
        def __init__(self, inner):
            self.inner = inner

        def table(self, name):
            if name == "notifications":
                raise ConnectionError("notifications insert refused")
            return self.inner.table(name)

    wrapped = NoNotifications(db)
    SupabaseRunLedger("p", lambda: wrapped, clock=Clock(NOW)).record(_run())
    [row] = db.table("scheduler_runs").inserted_payloads
    assert row["alerted"] is False
    assert any("alert FAILED" in r.getMessage() for r in caplog.records)


def test_register_jobs_upserts_the_schedules(db):
    _ledger(db, Clock(NOW)).register_jobs([
        JobSpec(job="nightly", cron="0 3 * * *", timezone="America/Sao_Paulo", misfire_grace_time=3600),
        JobSpec(job="tick", interval_seconds=60, timezone="America/Sao_Paulo"),
    ])
    rows = db.table("scheduler_jobs").upserted_payloads
    flat = [r for batch in rows for r in (batch if isinstance(batch, list) else [batch])]
    assert {r["job"] for r in flat} == {"nightly", "tick"}
    assert all(r["product"] == "social-wiring" and r["last_seen_at"] == NOW.isoformat() for r in flat)


def test_error_text_is_redacted_and_capped():
    raw = ("token=abc123secret Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijk "
           "postgres://user:hunter2@db.host/x mail joao@example.com sk-proj-ABCDEFGHIJKLMNOP " + "x" * 2000)
    out = sanitize_error(raw)
    assert "abc123secret" not in out
    assert "hunter2" not in out
    assert "joao@example.com" not in out
    assert "sk-proj-ABCDEFGHIJKLMNOP" not in out
    assert "eyJhbGciOiJIUzI1NiJ9" not in out
    assert len(out) <= 1000
    assert sanitize_error(None) is None


def test_factory_without_core_client_is_the_fake():
    assert isinstance(make_run_ledger("p", None), FakeRunLedger)
    assert isinstance(make_run_ledger("p", lambda: None), SupabaseRunLedger)
