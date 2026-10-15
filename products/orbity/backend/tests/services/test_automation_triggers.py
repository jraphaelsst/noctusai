"""disparar(): matching, idempotency, failure isolation, subjects."""
from __future__ import annotations

import uuid

from noctusai_lib.testing import MockSupabaseClient

from app.services.automation_triggers import LIVE_TRIGGERS, disparar

ORG = "00000000-0000-0000-0000-000000000042"
LEAD = str(uuid.uuid4())


def _db(flows, steps=None, extra_tables=()):
    db = MockSupabaseClient(schema="orbity")
    db.set_table_data("automation_flows", flows)
    db.set_table_data("automation_steps", steps if steps is not None else [
        {"id": str(uuid.uuid4()), "org_id": ORG, "flow_id": f["id"], "ord": 0,
         "step_type": "end", "config": {}} for f in flows
    ])
    db.set_table_data("automation_executions", [])
    db.set_table_data("automation_pending_actions", [])
    db.set_table_data("leads", [{"id": LEAD, "org_id": ORG, "name": "Maria", "phone": "5511999998888"}])
    for t in ("clients", "tasks", "agenda_events"):
        db.set_table_data(t, [])
    return db


def _flow(trigger_type, *, config=None, active=True, org=ORG):
    return {
        "id": str(uuid.uuid4()), "org_id": org, "name": "F", "trigger_type": trigger_type,
        "trigger_config": config or {}, "active": active, "schedule_window": {}, "stop_rules": {},
    }


def _execs(db):
    return db.table("automation_executions").select("*").execute().data


class TestMatching:
    def test_starts_each_active_flow_of_the_trigger_type(self):
        db = _db([_flow("lead_created"), _flow("lead_created"), _flow("task_created")])
        started = disparar("lead_created", ORG, lead_id=LEAD, db=db)
        assert len(started) == 2 and len(_execs(db)) == 2

    def test_inactive_flows_do_not_fire(self):
        db = _db([_flow("lead_created", active=False)])
        assert disparar("lead_created", ORG, lead_id=LEAD, db=db) == []

    def test_other_org_flows_do_not_fire(self):
        db = _db([_flow("lead_created", org="00000000-0000-0000-0000-000000000099")])
        assert disparar("lead_created", ORG, lead_id=LEAD, db=db) == []

    def test_stage_filter(self):
        f_any = _flow("pipeline_stage_entered")
        f_s1 = _flow("pipeline_stage_entered", config={"stage_id": "s1"})
        f_s2 = _flow("pipeline_stage_entered", config={"stage_id": "s2"})
        db = _db([f_any, f_s1, f_s2])
        started = disparar(
            "pipeline_stage_entered", ORG, lead_id=LEAD, payload={"stage_id": "s1"},
            trigger_key="stage:1", db=db,
        )
        assert {e["flow_id"] for e in started} == {f_any["id"], f_s1["id"]}

    def test_status_filter(self):
        won = _flow("lead_status_changed", config={"status": "won"})
        lost = _flow("lead_status_changed", config={"status": "lost"})
        db = _db([won, lost])
        started = disparar(
            "lead_status_changed", ORG, lead_id=LEAD, payload={"status": "won"},
            trigger_key="s:1", db=db,
        )
        assert [e["flow_id"] for e in started] == [won["id"]]

    def test_keyword_is_case_insensitive_contains_and_empty_keyword_never_fires(self):
        hit = _flow("keyword_received", config={"keyword": "ORÇAMENTO"})
        miss = _flow("keyword_received", config={"keyword": "preço"})
        empty = _flow("keyword_received", config={})
        db = _db([hit, miss, empty])
        started = disparar(
            "keyword_received", ORG, lead_id=LEAD,
            payload={"text": "Quero um orçamento, por favor"}, trigger_key="m:1", db=db,
        )
        assert [e["flow_id"] for e in started] == [hit["id"]]


class TestIdempotency:
    def test_same_occurrence_twice_starts_once(self):
        db = _db([_flow("lead_created")])
        assert len(disparar("lead_created", ORG, lead_id=LEAD, db=db)) == 1
        assert disparar("lead_created", ORG, lead_id=LEAD, db=db) == []
        assert len(_execs(db)) == 1

    def test_new_occurrence_key_starts_again(self):
        db = _db([_flow("pipeline_stage_entered")])
        disparar("pipeline_stage_entered", ORG, lead_id=LEAD, payload={"stage_id": "s"}, trigger_key="stage:a", db=db)
        disparar("pipeline_stage_entered", ORG, lead_id=LEAD, payload={"stage_id": "s"}, trigger_key="stage:b", db=db)
        assert len(_execs(db)) == 2


class TestSubjects:
    def test_task_subject(self):
        db = _db([_flow("task_created")])
        tid = str(uuid.uuid4())
        started = disparar("task_created", ORG, subject_type="task", subject_id=tid, db=db)
        assert started[0]["subject_type"] == "task" and started[0]["subject_id"] == tid
        assert started[0]["lead_id"] is None

    def test_missing_subject_is_ignored_not_raised(self):
        db = _db([_flow("task_created")])
        assert disparar("task_created", ORG, db=db) == []


class TestNeverRaises:
    def test_db_failure_is_swallowed(self):
        class Broken:
            def table(self, name):
                raise RuntimeError("db down")

        assert disparar("lead_created", ORG, lead_id=LEAD, db=Broken()) == []

    def test_a_failing_flow_is_recorded_failed_and_does_not_block_others(self):
        good = _flow("lead_created")
        bad = _flow("lead_created")
        steps = [
            {"id": str(uuid.uuid4()), "org_id": ORG, "flow_id": good["id"], "ord": 0,
             "step_type": "end", "config": {}},
            # malformed wait => the engine raises while advancing this flow
            {"id": str(uuid.uuid4()), "org_id": ORG, "flow_id": bad["id"], "ord": 0,
             "step_type": "wait", "config": {"duration_minutes": "abc"}},
        ]
        db = _db([good, bad], steps=steps)
        started = disparar("lead_created", ORG, lead_id=LEAD, db=db)
        assert [e["flow_id"] for e in started] == [good["id"]]
        failed = [e for e in _execs(db) if e["status"] == "failed"]
        assert len(failed) == 1 and failed[0]["flow_id"] == bad["id"]
        assert "Falha" in failed[0]["error_detail"]


def test_live_trigger_set_is_the_documented_one():
    assert LIVE_TRIGGERS == {
        "lead_created", "pipeline_stage_entered", "lead_status_changed", "task_created",
        "client_created", "meeting_created", "task_completed",
        "whatsapp_message_received", "keyword_received", "manual",
    }
