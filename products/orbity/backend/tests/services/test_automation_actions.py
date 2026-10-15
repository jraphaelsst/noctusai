"""`action` step executor: supported types act, everything else fails loudly."""
from __future__ import annotations

import uuid

import pytest
from noctusai_lib.testing import MockSupabaseClient

from app.services.automation_actions import SUPPORTED_ACTION_TYPES, execute_action
from app.services.automation_engine import ActionError

ORG = "00000000-0000-0000-0000-000000000042"
LEAD = str(uuid.uuid4())


def _db():
    db = MockSupabaseClient(schema="orbity")
    db.set_table_data("leads", [{"id": LEAD, "org_id": ORG, "name": "M", "tags": ["a"], "stage_id": None, "won_at": None}])
    db.set_table_data("lead_stages", [{"id": "s2", "org_id": ORG, "name": "Proposta", "is_won": False, "is_lost": False}])
    db.set_table_data("lead_activities", [])
    db.set_table_data("tasks", [])
    return db


def _p(action_type, **config):
    return {"action_type": action_type, "config": config, "subject_type": "lead", "subject_id": LEAD, "lead_id": LEAD}


def _lead(db):
    return db.table("leads").select("*").execute().data[0]


def test_add_and_remove_tag():
    db = _db()
    execute_action(db, ORG, _p("add_tag", tag="b"))
    assert _lead(db)["tags"] == ["a", "b"]
    execute_action(db, ORG, _p("add_tag", tag="b"))  # idempotent
    assert _lead(db)["tags"] == ["a", "b"]
    execute_action(db, ORG, _p("remove_tag", tag="a"))
    assert _lead(db)["tags"] == ["b"]


def test_move_stage():
    db = _db()
    execute_action(db, ORG, _p("move_stage", stage_id="s2"))
    assert _lead(db)["stage_id"] == "s2"
    assert db.table("lead_activities").select("*").execute().data[0]["type"] == "stage_move"


def test_move_to_unknown_stage_fails_ptbr():
    with pytest.raises(ActionError, match="Etapa de destino"):
        execute_action(_db(), ORG, _p("move_stage", stage_id="nope"))


def test_set_temperature_validates():
    db = _db()
    execute_action(db, ORG, _p("set_temperature", temperature="hot"))
    assert _lead(db)["temperature"] == "hot"
    with pytest.raises(ActionError):
        execute_action(db, ORG, _p("set_temperature", temperature="lava"))


def test_create_task_for_a_client_subject_links_client():
    db = _db()
    cid = str(uuid.uuid4())
    payload = {"action_type": "create_task", "config": {"title": "Ligar"},
               "subject_type": "client", "subject_id": cid}
    execute_action(db, ORG, payload)
    t = db.table("tasks").select("*").execute().data[0]
    assert t["title"] == "Ligar" and t["client_id"] == cid


@pytest.mark.parametrize("bad", [
    _p("teleport"), _p(""), _p("add_tag"), _p("move_stage"), _p("create_task"),
])
def test_unsupported_or_incomplete_actions_raise(bad):
    with pytest.raises(ActionError):
        execute_action(_db(), ORG, bad)


def test_lead_only_action_on_non_lead_subject_raises():
    payload = {"action_type": "add_tag", "config": {"tag": "x"}, "subject_type": "task", "subject_id": "t"}
    with pytest.raises(ActionError, match="fluxos de lead"):
        execute_action(_db(), ORG, payload)


def test_supported_set():
    assert SUPPORTED_ACTION_TYPES == {"add_tag", "remove_tag", "move_stage", "move_lead_stage",
                                      "set_temperature", "create_task"}
