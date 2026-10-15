"""
End-to-end (service level) tests for the LIVE automation engine:

  start -> advance chain -> scheduled send -> drain (claim + REAL-shaped send)
  -> advance -> next step ... -> done

over the stateful MockSupabaseClient with the seed `FakeWahaClient` behind the
real `RealWhatsAppSender` (explicit allow_fake injection), so the full path
sender -> WAHA client is exercised and `sent_messages` is asserted.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from uuid import UUID

import pytest
from noctusai_lib.testing import MockSupabaseClient

from app.services.automation_service import AutomationService
from app.services.automation_engine import FakeWhatsAppSender
from app.services.whatsapp_sender import RealWhatsAppSender

ORG = UUID("00000000-0000-0000-0000-000000000042")
ORG_S = str(ORG)
FLOW = str(uuid.uuid4())
LEAD = str(uuid.uuid4())
OPEN_WINDOW = {}  # no outside_window_behavior => pass-through, sends are due immediately


def _db(*, steps, lead=None, flow_extra=None):
    db = MockSupabaseClient(schema="orbity")
    db.set_table_data("automation_flows", [{
        "id": FLOW, "org_id": ORG_S, "name": "F", "trigger_type": "lead_created",
        "trigger_config": {}, "active": True, "schedule_window": OPEN_WINDOW,
        "stop_rules": {}, **(flow_extra or {}),
    }])
    db.set_table_data("automation_steps", [
        {"id": str(uuid.uuid4()), "org_id": ORG_S, "flow_id": FLOW, "ord": i, **s}
        for i, s in enumerate(steps)
    ])
    db.set_table_data("leads", [lead if lead is not None else {
        "id": LEAD, "org_id": ORG_S, "name": "Maria", "phone": "5511999998888",
        "tags": [], "custom_fields": {},
    }])
    db.set_table_data("automation_executions", [])
    db.set_table_data("automation_pending_actions", [])
    db.set_table_data("tasks", [])
    db.set_table_data("clients", [])
    db.set_table_data("agenda_events", [])
    return db


def _make_due(db):
    for a in db.table("automation_pending_actions").select("*").execute().data:
        db.table("automation_pending_actions").update(
            {"scheduled_for": "2020-01-01T00:00:00+00:00"}
        ).eq("id", a["id"]).execute()


def _rows(db, table):
    return db.table(table).select("*").execute().data


class TestEngineNoLongerStalls:
    def test_send_wait_send_runs_to_done_across_drains(self):
        db = _db(steps=[
            {"step_type": "send_message", "config": {"template": "Oi {nome}"}},
            {"step_type": "wait", "config": {"duration_minutes": 5}},
            {"step_type": "send_message", "config": {"template": "Segue o link"}},
        ])
        sender = FakeWhatsAppSender()
        svc = AutomationService(db, org_id=ORG, sender=sender)

        execution = svc.start_execution(FLOW, LEAD)
        assert execution["status"] == "running" and execution["current_step_ord"] == 1
        assert len(_rows(db, "automation_pending_actions")) == 1

        _make_due(db)
        svc.run_due()                      # sends "Oi Maria", advances onto the wait
        assert [m["message"] for m in sender.sent] == ["Oi Maria"]
        assert len(_rows(db, "automation_pending_actions")) == 2

        _make_due(db)
        svc.run_due()                      # wait over -> advances to the 3rd step (queues send)
        _make_due(db)
        svc.run_due()                      # sends the 3rd message
        assert [m["message"] for m in sender.sent] == ["Oi Maria", "Segue o link"]
        ex = _rows(db, "automation_executions")[0]
        assert ex["status"] == "done"
        assert all(a["status"] == "sent" for a in _rows(db, "automation_pending_actions"))

    def test_condition_and_branch_resolve_inline_in_one_chain(self):
        db = _db(steps=[
            {"step_type": "condition", "config": {"field": "name", "operator": "equals", "value": "Maria"}},
            {"step_type": "condition", "config": {"field": "name", "operator": "exists"}},
            {"step_type": "send_message", "config": {"template": "Olá"}},
        ])
        svc = AutomationService(db, org_id=ORG, sender=FakeWhatsAppSender())
        execution = svc.start_execution(FLOW, LEAD)
        # both conditions resolved without a scheduler tick; the send is queued
        assert len(_rows(db, "automation_pending_actions")) == 1
        assert execution["status"] in ("running", "done")

    def test_failed_send_stops_flow_with_ptbr_reason(self):
        db = _db(steps=[
            {"step_type": "send_message", "config": {"template": "Oi"}},
            {"step_type": "send_message", "config": {"template": "Segunda"}},
        ])
        # Real sender, fake NOT allowed, no connection => "WhatsApp não conectado"
        sender_stub = SimpleNamespace(
            encryption_key="", waha_base_url="", waha_api_key="", waha_session="default",
            waha_external_base_url="", whatsapp_allow_fake=False,
        )
        svc = AutomationService(db, org_id=ORG, sender=RealWhatsAppSender(lambda: db, sender_stub))
        svc.start_execution(FLOW, LEAD)
        _make_due(db)
        counts = svc.run_due()
        assert counts["failed"] == 1 and counts["sent"] == 0
        action = _rows(db, "automation_pending_actions")[0]
        assert action["status"] == "failed" and "WhatsApp não conectado" in action["error_detail"]
        ex = _rows(db, "automation_executions")[0]
        assert ex["status"] == "failed"

    def test_real_sender_over_fake_waha_records_the_message(self):
        from noctusai_lib.integrations.whatsapp import FakeWahaClient

        db = _db(steps=[{"step_type": "send_message", "config": {"template": "Oi {nome}"}}])
        waha = FakeWahaClient()
        stub = SimpleNamespace(whatsapp_allow_fake=False)
        sender = RealWhatsAppSender(lambda: db, stub, resolve_client=lambda **kw: waha)
        svc = AutomationService(db, org_id=ORG, sender=sender)
        svc.start_execution(FLOW, LEAD)
        _make_due(db)
        assert svc.run_due()["sent"] == 1
        assert waha.sent_messages[0]["chatId"] == "5511999998888@c.us"
        assert waha.sent_messages[0]["text"] == "Oi Maria"

    def test_default_sender_is_real_not_fake(self):
        from app.services.whatsapp_sender import RealWhatsAppSender as Real

        svc = AutomationService(MockSupabaseClient(schema="orbity"), org_id=ORG)
        assert isinstance(svc._sender, Real)

    def test_no_phone_send_is_skipped_and_recorded_on_the_execution(self):
        lead = {"id": LEAD, "org_id": ORG_S, "name": "Sem Fone", "phone": None, "tags": []}
        db = _db(lead=lead, steps=[
            {"step_type": "send_message", "config": {"template": "Oi"}},
            {"step_type": "end", "config": {}},
        ])
        svc = AutomationService(db, org_id=ORG, sender=FakeWhatsAppSender())
        svc.start_execution(FLOW, LEAD)
        ex = _rows(db, "automation_executions")[0]
        assert ex["context"]["skipped_steps"][0]["reason"] == "no_phone"


class TestIdempotentStart:
    def test_same_trigger_key_never_starts_the_flow_twice(self):
        db = _db(steps=[{"step_type": "send_message", "config": {"template": "Oi"}}])
        svc = AutomationService(db, org_id=ORG, sender=FakeWhatsAppSender())
        _, created1 = svc.start_execution_once(FLOW, LEAD, trigger_key="lead_created:x")
        _, created2 = svc.start_execution_once(FLOW, LEAD, trigger_key="lead_created:x")
        assert (created1, created2) == (True, False)
        assert len(_rows(db, "automation_executions")) == 1
        assert len(_rows(db, "automation_pending_actions")) == 1

    def test_different_key_starts_again(self):
        db = _db(steps=[{"step_type": "end", "config": {}}])
        svc = AutomationService(db, org_id=ORG, sender=FakeWhatsAppSender())
        svc.start_execution_once(FLOW, LEAD, trigger_key="k1")
        svc.start_execution_once(FLOW, LEAD, trigger_key="k2")
        assert len(_rows(db, "automation_executions")) == 2

    def test_unique_violation_race_returns_existing(self):
        """The INSERT loses a race (Postgres 23505) to a concurrent start of the
        same occurrence: the service returns the winner, not an error."""
        inner = _db(steps=[{"step_type": "end", "config": {}}])

        class UniqueViolation(Exception):
            code = "23505"

        class RacyDb:
            """Peer commits the same trigger_key right before our INSERT lands."""

            def __init__(self):
                self.raced = False

            def table(self, name):
                if name == "automation_executions" and not self.raced:
                    return _RacyTable(self)
                return inner.table(name)

        class _RacyTable:
            def __init__(self, outer):
                self._outer = outer

            def select(self, *a, **k):
                return inner.table("automation_executions").select(*a, **k)

            def insert(self, row):
                self._outer.raced = True
                inner.table("automation_executions").insert({**row, "status": "running"}).execute()
                raise UniqueViolation("duplicate key value violates unique constraint")

        svc = AutomationService(RacyDb(), org_id=ORG, sender=FakeWhatsAppSender())
        row, created = svc.start_execution_once(FLOW, LEAD, trigger_key="dup")
        assert created is False and row["trigger_key"] == "dup"
        assert len(_rows(inner, "automation_executions")) == 1


class TestNonLeadSubjects:
    def test_client_subject_reaches_the_clients_phone(self):
        db = _db(steps=[{"step_type": "send_message", "config": {"template": "Bem-vindo {nome}"}}])
        client_id = str(uuid.uuid4())
        db.set_table_data("clients", [{
            "id": client_id, "org_id": ORG_S, "name": "ACME", "phone": "5511988887777",
        }])
        sender = FakeWhatsAppSender()
        svc = AutomationService(db, org_id=ORG, sender=sender)
        ex, created = svc.start_execution_once(
            FLOW, None, subject_type="client", subject_id=client_id, trigger_key="client_created:1"
        )
        assert created and ex["lead_id"] is None and ex["subject_type"] == "client"
        _make_due(db)
        svc.run_due()
        assert sender.sent[0]["phone"] == "5511988887777"
        assert sender.sent[0]["message"] == "Bem-vindo ACME"

    def test_task_subject_without_client_skips_the_send_honestly(self):
        db = _db(steps=[{"step_type": "send_message", "config": {"template": "Oi"}}])
        task_id = str(uuid.uuid4())
        db.set_table_data("tasks", [{"id": task_id, "org_id": ORG_S, "title": "Ligar"}])
        svc = AutomationService(db, org_id=ORG, sender=FakeWhatsAppSender())
        svc.start_execution_once(FLOW, None, subject_type="task", subject_id=task_id)
        ex = _rows(db, "automation_executions")[0]
        assert ex["context"]["skipped_steps"][0]["reason"] == "no_phone"

    def test_meeting_subject_exposes_data_reuniao(self):
        db = _db(steps=[{"step_type": "send_message", "config": {"template": "Reunião {data_reuniao}"}}])
        client_id, ev = str(uuid.uuid4()), str(uuid.uuid4())
        db.set_table_data("clients", [{"id": client_id, "org_id": ORG_S, "name": "C", "phone": "5511977776666"}])
        db.set_table_data("agenda_events", [{
            "id": ev, "org_id": ORG_S, "client_id": client_id, "starts_at": "2026-11-01T13:00:00+00:00",
        }])
        sender = FakeWhatsAppSender()
        svc = AutomationService(db, org_id=ORG, sender=sender)
        svc.start_execution_once(FLOW, None, subject_type="meeting", subject_id=ev)
        _make_due(db)
        svc.run_due()
        assert "2026-11-01" in sender.sent[0]["message"]

    def test_subject_validation(self):
        svc = AutomationService(_db(steps=[]), org_id=ORG, sender=FakeWhatsAppSender())
        with pytest.raises(ValueError):
            svc.start_execution_once(FLOW, None)                       # lead without lead_id
        with pytest.raises(ValueError):
            svc.start_execution_once(FLOW, None, subject_type="task")  # task without subject_id
        with pytest.raises(ValueError):
            svc.start_execution_once(FLOW, None, subject_type="robot", subject_id="x")


class TestActionsEndToEnd:
    def test_add_tag_action_changes_the_lead_and_flow_completes(self):
        db = _db(steps=[
            {"step_type": "action", "config": {"action_type": "add_tag", "tag": "interessado"}},
            {"step_type": "end", "config": {}},
        ])
        svc = AutomationService(db, org_id=ORG, sender=FakeWhatsAppSender())
        svc.start_execution(FLOW, LEAD)
        _make_due(db)
        counts = svc.run_due()
        assert counts["sent"] == 1
        assert "interessado" in _rows(db, "leads")[0]["tags"]
        assert _rows(db, "automation_executions")[0]["status"] == "done"

    def test_unsupported_action_fails_explicitly(self):
        db = _db(steps=[{"step_type": "action", "config": {"action_type": "teleport"}}])
        svc = AutomationService(db, org_id=ORG, sender=FakeWhatsAppSender())
        svc.start_execution(FLOW, LEAD)
        _make_due(db)
        counts = svc.run_due()
        assert counts["failed"] == 1
        a = _rows(db, "automation_pending_actions")[0]
        assert a["status"] == "failed" and "não suportado" in a["error_detail"]

    def test_create_task_action(self):
        db = _db(steps=[{"step_type": "action", "config": {
            "action_type": "create_task", "title": "Follow-up comercial", "due_in_days": 2}}])
        svc = AutomationService(db, org_id=ORG, sender=FakeWhatsAppSender())
        svc.start_execution(FLOW, LEAD)
        _make_due(db)
        svc.run_due()
        task = _rows(db, "tasks")[0]
        assert task["title"] == "Follow-up comercial" and task["due_date"]


class TestStopOnReply:
    def test_reply_cancels_running_execution_by_default(self):
        db = _db(steps=[{"step_type": "wait", "config": {"duration_minutes": 60}},
                        {"step_type": "send_message", "config": {"template": "x"}}])
        svc = AutomationService(db, org_id=ORG, sender=FakeWhatsAppSender())
        svc.start_execution(FLOW, LEAD)
        assert svc.stop_on_reply(LEAD) == 1
        assert _rows(db, "automation_executions")[0]["status"] == "canceled"

    def test_flow_with_stop_on_reply_false_keeps_running_and_flags_replied(self):
        db = _db(steps=[{"step_type": "wait", "config": {"duration_minutes": 60}},
                        {"step_type": "send_message", "config": {"template": "x"}}],
                 flow_extra={"stop_rules": {"stop_on_reply": False}})
        svc = AutomationService(db, org_id=ORG, sender=FakeWhatsAppSender())
        svc.start_execution(FLOW, LEAD)
        assert svc.stop_on_reply(LEAD) == 0
        ex = _rows(db, "automation_executions")[0]
        assert ex["status"] == "running" and ex["context"]["lead_replied"] is True
