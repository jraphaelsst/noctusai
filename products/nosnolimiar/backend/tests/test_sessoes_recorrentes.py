"""Weekly care of Nós no Limiar: the clinic's session vocabulary, the daily materialization job, the clinical note's gate.

Pins: (a) the config is the clinic's (statuses, one week ahead, a falta charged unless the slot says otherwise, the
clinical note on); (b) the new routes are strictly 401 and the clinical note is 403 for any role but the therapist;
(c) the daily job creates the following week's session, is idempotent, catches up, and one org failing never costs the
others theirs; (d) the migrations carry the events / notes tables, service role only.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from noctusai_lib.domain.clients import ClientsService, FakeClientsStore
from noctusai_lib.domain.finance import FakeFinanceBooking
from noctusai_lib.testing.migrations import migration_sql

from app.crm import CLIENTS_CONFIG
from app.scheduler import SESSIONS_JOB, materialize_sessions

PRODUCT_DIR = Path(__file__).resolve().parents[1]
X = uuid.uuid4()
ORG_A = "11111111-1111-1111-1111-111111111111"
ORG_B = "22222222-2222-2222-2222-222222222222"
SP = timezone(timedelta(hours=-3))


class _Clock:
    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at.astimezone(timezone.utc)


def _service(store=None, clock=None):
    store = store or FakeClientsStore()
    return ClientsService(store, CLIENTS_CONFIG, FakeFinanceBooking(), clock=clock or _Clock(datetime(2026, 11, 3, 10, 0, tzinfo=SP))), store


# --- config ------------------------------------------------------------------------------------------------------------


def test_the_config_is_the_clinics_weekly_care():
    cfg = CLIENTS_CONFIG
    assert cfg.session_status_slugs == ("agendada", "realizada", "falta", "cancelada_paciente", "cancelada_terapeuta", "remarcada")
    assert [s for s in cfg.session_statuses if s.billable] and {s.slug for s in cfg.session_statuses if s.billable} == {"realizada", "falta"}
    assert (cfg.horizon_weeks, cfg.schedule_min_lead_days, tuple(cfg.absence_statuses), cfg.clinical_notes) == (1, 1, ("falta",), True)


def test_the_config_endpoint_tells_the_ui_about_absences_and_the_clinical_note(client):
    data = client.get("/api/clients/config").json()["data"]
    assert data["clinical_notes"] is True and data["absence_statuses"] == ["falta"] and data["done_session_status"] == "realizada"


# --- routes: auth ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/clients/summary?month=2026-11"), ("POST", f"/api/clients/sessions/{X}/reschedule"),
        ("GET", f"/api/clients/sessions/{X}/events"), ("GET", f"/api/clients/sessions/{X}/clinical-note"),
        ("PUT", f"/api/clients/sessions/{X}/clinical-note"), ("GET", f"/api/clients/{X}/events"),
    ],
)
def test_the_new_routes_are_strictly_401_without_auth(client, method, path):
    assert client.raw().request(method, path).status_code == 401


def test_the_clinical_note_is_403_for_a_member_who_is_not_the_therapist(client):
    """The gate runs before any lookup: a member learns nothing about whether the session or a note exists."""
    path = f"/api/clients/sessions/{X}/clinical-note"
    got, put = client.get(path), client.put(path, json={"body": "segredo clínico"})
    assert (got.status_code, put.status_code) == (403, 403), (got.text, put.text)
    assert "segredo" not in got.text + put.text  # nothing of the body is echoed


# --- the daily job -----------------------------------------------------------------------------------------------------


def _slot(svc, org=ORG_A, name="Ana"):
    pid = svc.create(org, {"name": name})["id"]
    svc.create_schedule(org, pid, {"weekday": 0, "time": "14:00", "price_cents": 20000})
    return pid


def _starts(svc, org, pid):
    return sorted(s["starts_at"][:16] for s in svc.client_sessions(org, pid))


def test_a_slot_set_on_a_tuesday_has_next_mondays_session_and_the_job_adds_the_following_week_on_the_day():
    clock = _Clock(datetime(2026, 11, 3, 10, 0, tzinfo=SP))  # Tuesday
    svc, _ = _service(clock=clock)
    pid = _slot(svc)
    assert _starts(svc, ORG_A, pid) == ["2026-11-09T14:00"]
    clock.at = datetime(2026, 11, 9, 8, 0, tzinfo=SP)  # that Monday: the job creates the following Monday's
    assert materialize_sessions(svc) == {ORG_A: 1}
    assert _starts(svc, ORG_A, pid) == ["2026-11-09T14:00", "2026-11-16T14:00"]
    assert materialize_sessions(svc) == {}  # idempotent


def test_the_job_catches_up_after_missed_days():
    clock = _Clock(datetime(2026, 11, 3, 10, 0, tzinfo=SP))
    svc, _ = _service(clock=clock)
    pid = _slot(svc)
    clock.at = datetime(2026, 11, 30, 8, 0, tzinfo=SP)  # three weeks with no run
    materialize_sessions(svc)
    assert _starts(svc, ORG_A, pid) == ["2026-11-09T14:00", "2026-11-30T14:00", "2026-12-07T14:00"]


def test_one_orgs_failure_is_logged_with_the_org_and_never_costs_the_others_their_sessions(caplog):
    class _Flaky(FakeClientsStore):
        def schedules_due(self, org_id, through, *, client_id=None):
            if org_id == ORG_A and getattr(self, "armed", False):
                raise RuntimeError("boom")
            return super().schedules_due(org_id, through, client_id=client_id)

    clock = _Clock(datetime(2026, 11, 3, 10, 0, tzinfo=SP))
    svc, store = _service(_Flaky(), clock)
    pa, pb = _slot(svc, ORG_A, "Ana"), _slot(svc, ORG_B, "Bia")
    store.armed = True
    clock.at = datetime(2026, 11, 9, 8, 0, tzinfo=SP)
    with caplog.at_level(logging.ERROR):
        made = materialize_sessions(svc)
    assert made == {ORG_B: 1}
    assert any(SESSIONS_JOB in r.getMessage() and ORG_A in r.getMessage() for r in caplog.records)
    store.armed = False
    assert _starts(svc, ORG_B, pb)[-1] == "2026-11-16T14:00"
    assert materialize_sessions(svc) == {ORG_A: 1}  # the failed org recovers on the next run
    assert _starts(svc, ORG_A, pa)[-1] == "2026-11-16T14:00"


def test_the_job_is_registered_daily_on_the_seed_scheduler():
    from noctusai_lib.api import scheduler as seed_scheduler

    from app.main import app  # noqa: F401 -- importing the app registers the jobs (configure() at import time)

    job = seed_scheduler.scheduler.get_job(SESSIONS_JOB)
    assert job is not None and "cron" in str(job.trigger).lower()


# --- the falta rule, end to end through the product config ------------------------------------------------------------


def test_a_falta_is_charged_unless_the_slot_waives_it():
    svc, _ = _service()
    pa = svc.create(ORG_A, {"name": "Ana"})["id"]
    pb = svc.create(ORG_A, {"name": "Bia"})["id"]
    svc.create_schedule(ORG_A, pa, {"weekday": 0, "time": "14:00", "price_cents": 20000})
    svc.create_schedule(ORG_A, pb, {"weekday": 0, "time": "15:00", "price_cents": 20000, "charge_absences": False})
    (sa,), (sb,) = svc.client_sessions(ORG_A, pa), svc.client_sessions(ORG_A, pb)
    assert svc.update_session(ORG_A, sa["id"], {"status": "falta"})["charge_status"] == "pendente"
    assert svc.update_session(ORG_A, sb["id"], {"status": "falta"})["charge_status"] == "isento"
    assert svc.client_finance(ORG_A, pa)["open_cents"] == 20000 and svc.client_finance(ORG_A, pb)["open_cents"] == 0


# --- migrations --------------------------------------------------------------------------------------------------------


def test_the_events_and_the_clinical_notes_are_service_role_only():
    sql = migration_sql(PRODUCT_DIR, "clients_rev2")
    for table in ("client_events", "client_session_notes"):
        assert f"ALTER TABLE nosnolimiar.{table} ENABLE ROW LEVEL SECURITY" in sql
        assert f"REVOKE ALL ON nosnolimiar.{table} FROM PUBLIC, anon, authenticated" in sql
        assert f'"{table}_select_own_org" ON nosnolimiar.{table};' in sql and "TO authenticated" not in sql.split(f"CREATE TABLE IF NOT EXISTS nosnolimiar.{table}")[1].split("CREATE TABLE")[0]
    assert "GRANT SELECT, INSERT ON nosnolimiar.client_events TO service_role" in sql  # append-only for the backend too
    assert "GRANT ALL ON nosnolimiar.client_events" not in sql


def test_the_cancelled_sessions_of_the_old_vocabulary_are_carried_over():
    sql = migration_sql(PRODUCT_DIR, "sessions_status_split")
    assert "SET status = 'cancelada_paciente'" in sql and "WHERE status = 'cancelada'" in sql
