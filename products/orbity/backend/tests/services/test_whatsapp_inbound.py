"""Inbound WhatsApp -> triggers: known leads only (shared WAHA session safe)."""
from __future__ import annotations

import uuid
from types import SimpleNamespace

from noctusai_lib.testing import MockSupabaseClient

from app.services.whatsapp_inbound import find_lead_by_phone, phone_candidates, process_inbound

ORG = "00000000-0000-0000-0000-000000000042"
LEAD = str(uuid.uuid4())


def _db(*, flows=(), leads=None, executions=()):
    db = MockSupabaseClient(schema="orbity")
    db.set_table_data("leads", leads if leads is not None else [
        {"id": LEAD, "org_id": ORG, "name": "Maria", "phone": "5511999998888", "created_at": "2026-01-01"}])
    db.set_table_data("automation_flows", list(flows))
    db.set_table_data("automation_steps", [
        {"id": str(uuid.uuid4()), "org_id": ORG, "flow_id": f["id"], "ord": 0, "step_type": "end", "config": {}}
        for f in flows])
    db.set_table_data("automation_executions", list(executions))
    db.set_table_data("automation_pending_actions", [])
    return db


def _flow(trigger_type, config=None, stop_rules=None):
    return {"id": str(uuid.uuid4()), "org_id": ORG, "name": "F", "trigger_type": trigger_type,
            "trigger_config": config or {}, "active": True, "schedule_window": {},
            "stop_rules": stop_rules or {}}


def _msg(phone="5511999998888", text="oi", mid="m1", group=None):
    return SimpleNamespace(from_phone=phone, text=text, provider_message_id=mid, group_id=group)


def test_ninth_digit_variants():
    assert set(phone_candidates("5511999998888")) == {"5511999998888", "551199998888"}
    # canonical normaliser rejects legacy 8-digit mobiles; the inbound (13-digit) side adds the variant
    assert phone_candidates("551199998888") == []
    assert set(phone_candidates("551132165498")) == {"551132165498"}
    assert phone_candidates("abc") == []


def test_finds_lead_with_or_without_ninth_digit():
    db = _db(leads=[{"id": LEAD, "org_id": ORG, "name": "M", "phone": "551199998888", "created_at": "x"}])
    assert find_lead_by_phone(db, ORG, "5511999998888")["id"] == LEAD


def test_unknown_sender_is_ignored_and_triggers_nothing():
    f = _flow("whatsapp_message_received")
    db = _db(flows=[f])
    out = process_inbound(db, ORG, _msg(phone="5521977770000"))
    assert out == {"handled": False, "reason": "unknown_sender"}
    assert db.table("automation_executions").select("*").execute().data == []


def test_group_messages_are_ignored():
    db = _db(flows=[_flow("whatsapp_message_received")])
    assert process_inbound(db, ORG, _msg(group="123@g.us"))["reason"] == "group"


def test_other_orgs_lead_is_not_matched():
    db = _db(leads=[{"id": LEAD, "org_id": "other-org", "name": "M", "phone": "5511999998888", "created_at": "x"}])
    assert process_inbound(db, ORG, _msg())["handled"] is False


def test_known_lead_fires_message_and_keyword_flows_once():
    any_msg = _flow("whatsapp_message_received")
    kw = _flow("keyword_received", {"keyword": "orçamento"})
    db = _db(flows=[any_msg, kw])
    out = process_inbound(db, ORG, _msg(text="Quero ORÇAMENTO"))
    assert out["handled"] and out["started"] == 2
    again = process_inbound(db, ORG, _msg(text="Quero ORÇAMENTO"))  # webhook redelivery
    assert again["started"] == 0
    assert len(db.table("automation_executions").select("*").execute().data) == 2


def test_reply_cancels_running_execution_of_stop_on_reply_flow():
    running_flow = _flow("lead_created")
    ex = {"id": str(uuid.uuid4()), "org_id": ORG, "flow_id": running_flow["id"], "lead_id": LEAD,
          "status": "running", "context": {}}
    db = _db(flows=[running_flow], executions=[ex])
    out = process_inbound(db, ORG, _msg())
    assert out["canceled"] == 1
    assert db.table("automation_executions").select("*").execute().data[0]["status"] == "canceled"
