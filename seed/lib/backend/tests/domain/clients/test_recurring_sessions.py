"""Recurring sessions, absences, events and the clinical note -- the clinic configuration of the clients organ.

Both stores run the same suite. The owner's example is pinned: a weekly slot set on a Tuesday for Monday 14:00 creates
NEXT Monday's session at once, and every Monday the following week's session is created (one week ahead, always).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from noctusai_lib.domain.clients import ClientsConfig, ClientsService, SessionStatus, create_clients_router
from noctusai_lib.domain.finance import FakeFinanceBooking
from noctusai_lib.primitives.exceptions import (
    AppException,
    NotFoundError,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)

from .conftest import ACCOUNT, ORG_A, ORG_B, Clock, _admin, _auth

CLINIC = ClientsConfig(
    noun_singular="Paciente",
    noun_plural="Pacientes",
    session_statuses=(
        SessionStatus("agendada", "Agendada", "primary"),
        SessionStatus("realizada", "Realizada", "success", billable=True),
        SessionStatus("falta", "Falta", "destructive", billable=True),
        SessionStatus("cancelada_paciente", "Cancelada pela paciente", "muted"),
        SessionStatus("cancelada_terapeuta", "Cancelada pela terapeuta", "muted"),
        SessionStatus("remarcada", "Remarcada", "warning"),
    ),
    absence_statuses=("falta",),
    schedule_min_lead_days=1,
    horizon_weeks=1,
    clinical_notes=True,
)

SP = timezone(timedelta(hours=-3))
#: Tuesday 2026-11-03 10:00 in São Paulo
TUESDAY = datetime(2026, 11, 3, 10, 0, tzinfo=SP)
MONDAY_1 = date(2026, 11, 9)
NOTE = "Falou do luto do pai; resistência ao tema do dinheiro."


@pytest.fixture
def clock() -> Clock:
    return Clock(TUESDAY.astimezone(timezone.utc))


@pytest.fixture
def svc(store, booking, clock) -> ClientsService:
    return ClientsService(store, CLINIC, booking, clock=clock)


def _at(day: date, hh: int, mm: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=SP)


def _patient(svc, **kw):
    return svc.create(ORG_A, {"name": "Ana", **kw}, is_admin=True)


def _weekly(svc, cid, **kw):
    body = {"weekday": 0, "time": "14:00", "price_cents": 20000, **kw}
    return svc.create_schedule(ORG_A, cid, body)


def _sessions(svc, cid):
    return sorted(svc.client_sessions(ORG_A, cid), key=lambda s: s["starts_at"])


def _starts(svc, cid):
    return [s["starts_at"][:16] for s in _sessions(svc, cid)]


# -- the owner's example --------------------------------------------------------------------------------


def test_set_on_a_tuesday_creates_next_mondays_session_only(svc):
    cid = _patient(svc)["id"]
    sched = _weekly(svc, cid)
    assert sched["status"] == "ativa" and sched["charge_absences"] is True
    assert _starts(svc, cid) == ["2026-11-09T14:00"]


def test_set_on_the_slots_own_weekday_starts_a_week_later(svc, clock):
    clock.at = _at(date(2026, 11, 2), 9).astimezone(timezone.utc)  # Monday morning, slot Monday 14:00
    cid = _patient(svc)["id"]
    _weekly(svc, cid)
    assert _starts(svc, cid) == ["2026-11-09T14:00"]  # never today: the first session is at least a day ahead


def test_every_monday_the_following_weeks_session_is_created(svc, clock):
    cid = _patient(svc)["id"]
    _weekly(svc, cid)
    clock.at = _at(MONDAY_1, 8).astimezone(timezone.utc)
    assert svc.materialize_due() == {ORG_A: 1}
    assert _starts(svc, cid) == ["2026-11-09T14:00", "2026-11-16T14:00"]
    clock.at = _at(date(2026, 11, 16), 8).astimezone(timezone.utc)
    assert svc.materialize_due() == {ORG_A: 1}
    assert _starts(svc, cid)[-1] == "2026-11-23T14:00"


def test_the_job_is_idempotent_and_a_missed_run_catches_up(svc, clock):
    cid = _patient(svc)["id"]
    _weekly(svc, cid)
    clock.at = _at(MONDAY_1, 8).astimezone(timezone.utc)
    svc.materialize_due()
    assert svc.materialize_due() == {}  # same day again: nothing new
    assert _starts(svc, cid) == ["2026-11-09T14:00", "2026-11-16T14:00"]
    clock.at = _at(date(2026, 11, 30), 8).astimezone(timezone.utc)  # the job did not run for three weeks
    svc.materialize_due()
    assert _starts(svc, cid) == [
        "2026-11-09T14:00", "2026-11-16T14:00", "2026-11-30T14:00", "2026-12-07T14:00",
    ]  # past occurrences are not invented; every future one up to the horizon is
    assert svc.materialize_due() == {}


def test_a_paused_slot_creates_nothing_and_resuming_catches_up(svc, clock):
    cid = _patient(svc)["id"]
    sched = _weekly(svc, cid)
    svc.update_schedule(ORG_A, sched["id"], {"active": False})
    assert _starts(svc, cid) == [] and svc.list_schedules(ORG_A, cid)[0]["status"] == "pausada"
    clock.at = _at(MONDAY_1, 8).astimezone(timezone.utc)
    assert svc.materialize_due() == {}
    svc.update_schedule(ORG_A, sched["id"], {"active": True})
    assert _starts(svc, cid) == ["2026-11-09T14:00", "2026-11-16T14:00"]


# -- the series survives single-occurrence changes ------------------------------------------------------


def test_cancelling_one_occurrence_never_regenerates_it_nor_breaks_the_series(svc, clock):
    cid = _patient(svc)["id"]
    _weekly(svc, cid)
    first = _sessions(svc, cid)[0]
    svc.update_session(ORG_A, first["id"], {"status": "cancelada_paciente"})
    clock.at = _at(MONDAY_1, 8).astimezone(timezone.utc)
    svc.materialize_due()
    svc.materialize_due()
    rows = _sessions(svc, cid)
    assert [(s["starts_at"][:10], s["status"]) for s in rows] == [
        ("2026-11-09", "cancelada_paciente"), ("2026-11-16", "agendada"),
    ]
    assert rows[0]["charge_status"] == "cancelado" and rows[1]["charge_status"] is None


def test_reschedule_marks_remarcada_and_creates_the_new_time_without_touching_the_series(svc, clock):
    cid = _patient(svc)["id"]
    _weekly(svc, cid)
    first = _sessions(svc, cid)[0]
    new = svc.reschedule_session(ORG_A, first["id"], _at(date(2026, 11, 11), 16), user_id="u1")
    assert new["status"] == "agendada" and new["schedule_id"] is None and new["starts_at"][:16] == "2026-11-11T16:00"
    clock.at = _at(MONDAY_1, 8).astimezone(timezone.utc)
    svc.materialize_due()
    rows = _sessions(svc, cid)
    assert [(s["starts_at"][:10], s["status"]) for s in rows] == [
        ("2026-11-09", "remarcada"), ("2026-11-11", "agendada"), ("2026-11-16", "agendada"),
    ]
    created = [e for e in svc.session_events(ORG_A, new["id"]) if e["kind"] == "session_created"]
    assert created[0]["data"]["rescheduled_from"] == first["id"] and created[0]["actor"] == "u1"


def test_editing_the_slot_follows_the_existing_future_session_by_default(svc):
    cid = _patient(svc)["id"]
    sched = _weekly(svc, cid)
    svc.update_schedule(ORG_A, sched["id"], {"time": "15:00", "price_cents": 25000})
    only = _sessions(svc, cid)
    assert [s["starts_at"][:16] for s in only] == ["2026-11-09T15:00"] and only[0]["amount_cents"] == 25000


def test_editing_the_slot_can_leave_the_session_already_created_alone(svc, clock):
    cid = _patient(svc)["id"]
    sched = _weekly(svc, cid)
    svc.update_schedule(ORG_A, sched["id"], {"time": "15:00"}, apply_to_existing=False)
    assert _starts(svc, cid) == ["2026-11-09T14:00"]  # kept as it was
    clock.at = _at(MONDAY_1, 8).astimezone(timezone.utc)
    svc.materialize_due()
    assert _starts(svc, cid) == ["2026-11-09T14:00", "2026-11-16T15:00"]  # the new shape only from there on


def test_ending_a_slot_is_encerrada_and_stops_generating(svc, clock):
    cid = _patient(svc)["id"]
    sched = _weekly(svc, cid)
    svc.update_schedule(ORG_A, sched["id"], {"ends_on": date(2026, 11, 9)})
    clock.at = _at(MONDAY_1, 8).astimezone(timezone.utc)
    svc.materialize_due()
    assert _starts(svc, cid) == ["2026-11-09T14:00"]
    assert svc.list_schedules(ORG_A, cid)[0]["status"] == "encerrada"


# -- falta, payments ------------------------------------------------------------------------------------


def test_an_absence_is_charged_by_default_and_waived_when_the_slot_says_so(svc):
    a, b = _patient(svc)["id"], svc.create(ORG_A, {"name": "Bia"})["id"]
    _weekly(svc, a)
    _weekly(svc, b, charge_absences=False)
    sa, sb = _sessions(svc, a)[0], _sessions(svc, b)[0]
    assert svc.update_session(ORG_A, sa["id"], {"status": "falta"})["charge_status"] == "pendente"
    missed = svc.update_session(ORG_A, sb["id"], {"status": "falta"})
    assert missed["charge_status"] == "isento" and missed["entry_id"] is None
    # ...but a session that HAPPENED is always charged
    assert svc.update_session(ORG_A, sb["id"], {"status": "realizada"})["charge_status"] == "pendente"
    assert svc.client_finance(ORG_A, a)["open_cents"] == 20000


def test_payment_per_session_flips_it_to_pago_and_is_an_event(svc):
    cid = _patient(svc)["id"]
    _weekly(svc, cid)
    sess = svc.update_session(ORG_A, _sessions(svc, cid)[0]["id"], {"status": "realizada"}, user_id="u1")
    assert (sess["charge_status"], sess["amount_cents"], sess["settled_cents"]) == ("pendente", 20000, 0)
    out = svc.record_payment(
        ORG_A, cid,
        {"amount_cents": 20000, "paid_on": date(2026, 11, 9), "account_id": ACCOUNT, "method": "pix", "entry_ids": [sess["entry_id"]]},
        user_id="u1",
    )
    assert out["finance"]["open_cents"] == 0
    paid = _sessions(svc, cid)[0]
    assert (paid["charge_status"], paid["settled_cents"]) == ("pago", 20000)
    kinds = [e["kind"] for e in svc.session_events(ORG_A, sess["id"])]
    assert kinds == ["session_materialized", "session_status_changed", "payment_recorded"]
    pay = svc.session_events(ORG_A, sess["id"])[-1]
    assert pay["data"]["method"] == "pix" and pay["data"]["amount_cents"] == 20000 and pay["actor"] == "u1"


def test_month_summary_counts_charged_received_and_open(svc, clock):
    cid = _patient(svc)["id"]
    _weekly(svc, cid)
    clock.at = _at(MONDAY_1, 8).astimezone(timezone.utc)
    svc.materialize_due()
    first, second = _sessions(svc, cid)
    done = svc.update_session(ORG_A, first["id"], {"status": "realizada"})
    svc.update_session(ORG_A, second["id"], {"status": "falta"})
    svc.record_payment(
        ORG_A, cid, {"amount_cents": 20000, "paid_on": date(2026, 11, 9), "account_id": ACCOUNT, "method": "dinheiro", "entry_ids": [done["entry_id"]]},
    )
    m = svc.month_summary(ORG_A, 2026, 11)
    assert m["month"] == "2026-11" and m["sessions"] == 2
    assert m["by_status"]["realizada"] == 1 and m["by_status"]["falta"] == 1 and m["by_status"]["agendada"] == 0
    assert (m["charged_cents"], m["received_cents"], m["open_cents"]) == (40000, 20000, 20000)
    assert svc.month_summary(ORG_A, 2026, 12)["sessions"] == 0
    assert svc.month_summary(ORG_B, 2026, 11)["sessions"] == 0


# -- events ---------------------------------------------------------------------------------------------


def test_schedule_lifecycle_is_an_event_log_with_the_actor(svc):
    cid = _patient(svc)["id"]
    sched = svc.create_schedule(ORG_A, cid, {"weekday": 0, "time": "14:00", "price_cents": 20000}, user_id="u1")
    svc.update_schedule(ORG_A, sched["id"], {"active": False}, user_id="u2")
    svc.update_schedule(ORG_A, sched["id"], {"active": True, "price_cents": 22000}, user_id="u2")
    svc.delete_schedule(ORG_A, sched["id"], user_id="u3")
    log = [(e["kind"], e["actor"]) for e in svc.client_events(ORG_A, cid) if e["schedule_id"] == sched["id"] and e["kind"] != "session_materialized"]
    assert log == [
        ("schedule_created", "u1"), ("schedule_paused", "u2"), ("schedule_resumed", "u2"), ("schedule_changed", "u2"), ("schedule_deleted", "u3"),
    ]


# -- the clinical note ----------------------------------------------------------------------------------


def test_the_clinical_note_lives_apart_and_never_reaches_a_session_payload_or_an_event(svc, store):
    cid = _patient(svc)["id"]
    _weekly(svc, cid)
    sid = _sessions(svc, cid)[0]["id"]
    svc.update_session(ORG_A, sid, {"notes": "chegou atrasada"})
    saved = svc.set_clinical_note(ORG_A, sid, f"  {NOTE} ", user_id="u1")
    assert saved["body"] == NOTE and saved["updated_by"] == "u1"
    assert svc.get_clinical_note(ORG_A, sid)["body"] == NOTE
    payloads = [svc.agenda(ORG_A, date(2026, 11, 9), date(2026, 11, 9)), svc.client_sessions(ORG_A, cid)]
    for rows in payloads:
        blob = repr(rows)
        assert NOTE not in blob and "clinical" not in blob and "anotac" not in blob
        assert rows[0]["notes"] == "chegou atrasada"  # the administrative note stays where the agenda is managed
    events = repr(svc.session_events(ORG_A, sid)) + repr(svc.client_events(ORG_A, cid))
    assert NOTE not in events and "chegou atrasada" not in events and "clinical_note_saved" in events
    assert NOTE not in repr(svc.get(ORG_A, cid, is_admin=True))


def test_the_clinical_note_is_org_scoped_validated_and_switchable(svc, store, booking, clock):
    cid = _patient(svc)["id"]
    _weekly(svc, cid)
    sid = _sessions(svc, cid)[0]["id"]
    assert svc.get_clinical_note(ORG_A, sid)["body"] == ""
    with pytest.raises(NotFoundError):
        svc.get_clinical_note(ORG_B, sid)
    with pytest.raises(NotFoundError):
        svc.set_clinical_note(ORG_B, sid, "x")
    for bad in ("   ", "x" * 20_001):
        with pytest.raises(Exception) as e:
            svc.set_clinical_note(ORG_A, sid, bad)
        assert e.value.code == "anotacao_invalida"
    off = ClientsService(store, ClientsConfig(), booking, clock=clock)
    with pytest.raises(NotFoundError):
        off.get_clinical_note(ORG_A, sid)


# -- HTTP -----------------------------------------------------------------------------------------------


@pytest.fixture
def api(store, booking, clock):
    router = create_clients_router(
        store_factory=lambda: store, get_current_user_org=_auth, admin_dependency=_admin, config=CLINIC,
        booking_factory=lambda: booking, clock=clock,
    )
    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.include_router(router)
    return TestClient(app)


MEMBER = {"Authorization": "Bearer org-a"}
THERAPIST = {"Authorization": "Bearer org-a-admin"}
X = "00000000-0000-4000-8000-000000000009"


@pytest.mark.parametrize("method, path", [
    ("get", "/api/clients/summary?month=2026-11"),
    ("post", f"/api/clients/sessions/{X}/reschedule"),
    ("get", f"/api/clients/sessions/{X}/events"),
    ("get", f"/api/clients/sessions/{X}/clinical-note"),
    ("put", f"/api/clients/sessions/{X}/clinical-note"),
    ("get", f"/api/clients/{X}/events"),
])
def test_new_routes_are_strictly_401_without_auth(api, method, path):
    kw = {"json": {}} if method in ("post", "put") else {}
    assert getattr(api, method)(path, **kw).status_code == 401


def _seed(api):
    cid = api.post("/api/clients", json={"name": "Ana"}, headers=MEMBER).json()["data"]["id"]
    made = api.post(f"/api/clients/{cid}/schedules", json={"weekday": 0, "time": "14:00", "price_cents": 20000}, headers=MEMBER)
    assert made.status_code == 201 and made.json()["data"]["charge_absences"] is True
    sid = api.get(f"/api/clients/{cid}/sessions", headers=MEMBER).json()["data"][0]["id"]
    return cid, sid


def test_clinical_note_is_therapist_only_and_absent_from_every_list(api):
    cid, sid = _seed(api)
    path = f"/api/clients/sessions/{sid}/clinical-note"
    assert api.get(path, headers=MEMBER).status_code == 403
    assert api.put(path, json={"body": NOTE}, headers=MEMBER).status_code == 403
    assert api.get(path, headers={"Authorization": "Bearer org-b-admin"}).status_code == 404  # another org's therapist
    assert api.put(path, json={"body": NOTE}, headers=THERAPIST).json()["data"]["body"] == NOTE
    assert api.get(path, headers=THERAPIST).json()["data"]["body"] == NOTE
    for url in (
        f"/api/clients/{cid}/sessions", "/api/clients/sessions?from=2026-11-01&to=2026-11-30",
        f"/api/clients/sessions/{sid}/events", f"/api/clients/{cid}/events", f"/api/clients/{cid}", "/api/clients",
    ):
        for headers in (MEMBER, THERAPIST):
            text = api.get(url, headers=headers).text
            assert NOTE not in text, url
    assert api.put(path, json={"body": "  "}, headers=THERAPIST).status_code == 422
    assert api.put(path, json={"body": NOTE, "extra": 1}, headers=THERAPIST).status_code == 422  # strict body


def test_summary_reschedule_and_events_over_http(api, clock):
    cid, sid = _seed(api)
    clock.at += timedelta(minutes=1)  # one service per request: a frozen clock would tie the two requests' events
    moved = api.post(f"/api/clients/sessions/{sid}/reschedule", json={"starts_at": "2026-11-11T16:00:00-03:00"}, headers=MEMBER)
    assert moved.status_code == 201 and moved.json()["data"]["starts_at"].startswith("2026-11-11T16:00")
    kinds = [e["kind"] for e in api.get(f"/api/clients/sessions/{sid}/events", headers=MEMBER).json()["data"]]
    assert kinds[:2] == ["session_materialized", "session_status_changed"]
    month = api.get("/api/clients/summary?month=2026-11", headers=MEMBER).json()["data"]
    assert month["sessions"] == 2 and month["by_status"]["remarcada"] == 1
    assert api.get("/api/clients/summary?month=2026-13", headers=MEMBER).status_code == 422
    sched = api.get(f"/api/clients/{cid}/schedules", headers=MEMBER).json()["data"][0]
    off = api.patch(f"/api/clients/schedules/{sched['id']}", json={"charge_absences": False, "apply_to_existing": False}, headers=MEMBER)
    assert off.status_code == 200 and off.json()["data"]["charge_absences"] is False
