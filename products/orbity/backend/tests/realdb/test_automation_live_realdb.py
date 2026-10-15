"""Real-DB checks for the automation-live migration (idempotency key, non-lead subject, claim CAS).

REQUIRES the automation_live migration applied. Every test skips cleanly when
its objects are absent (table / column probe) or Supabase creds are unset.
The tech-lead applies the migration at integration time.
"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.realdb


@pytest.fixture(scope="module", autouse=True)
def _require_automation_live(orbity_db):
    try:
        orbity_db.table("whatsapp_connections").select("id").limit(1).execute()
        orbity_db.table("automation_executions").select("trigger_key,subject_type").limit(1).execute()
        orbity_db.table("automation_pending_actions").select("claimed_at").limit(1).execute()
    except Exception as exc:  # noqa: BLE001 — PGRST/42703 => not applied yet
        pytest.skip(f"automation_live migration not applied: {type(exc).__name__}")


def _flow(db, org_id):
    return db.table("automation_flows").insert({
        "org_id": org_id, "name": "rt", "trigger_type": "task_created"}).execute().data[0]


def test_trigger_key_is_unique_per_flow(orbity_db, test_org_a):
    org = test_org_a["id"]
    flow = _flow(orbity_db, org)
    try:
        row = {"org_id": org, "flow_id": flow["id"], "subject_type": "task",
               "subject_id": str(uuid.uuid4()), "trigger_key": "k1"}
        orbity_db.table("automation_executions").insert(row).execute()
        with pytest.raises(Exception) as exc:
            orbity_db.table("automation_executions").insert(row).execute()
        assert "23505" in str(exc.value) or "duplicate" in str(exc.value).lower()
    finally:
        orbity_db.table("automation_flows").delete().eq("id", flow["id"]).execute()


def test_non_lead_subject_needs_subject_id_and_lead_needs_lead_id(orbity_db, test_org_a):
    org = test_org_a["id"]
    flow = _flow(orbity_db, org)
    try:
        with pytest.raises(Exception):  # task subject without subject_id
            orbity_db.table("automation_executions").insert(
                {"org_id": org, "flow_id": flow["id"], "subject_type": "task"}).execute()
        with pytest.raises(Exception):  # default lead subject without lead_id
            orbity_db.table("automation_executions").insert(
                {"org_id": org, "flow_id": flow["id"]}).execute()
    finally:
        orbity_db.table("automation_flows").delete().eq("id", flow["id"]).execute()


def test_claim_compare_and_set_lets_exactly_one_winner(orbity_db, test_org_a):
    org = test_org_a["id"]
    flow = _flow(orbity_db, org)
    try:
        step = orbity_db.table("automation_steps").insert({
            "org_id": org, "flow_id": flow["id"], "ord": 0, "step_type": "end"}).execute().data[0]
        ex = orbity_db.table("automation_executions").insert({
            "org_id": org, "flow_id": flow["id"], "subject_type": "task",
            "subject_id": str(uuid.uuid4())}).execute().data[0]
        act = orbity_db.table("automation_pending_actions").insert({
            "org_id": org, "execution_id": ex["id"], "step_id": step["id"],
            "scheduled_for": "2020-01-01T00:00:00+00:00"}).execute().data[0]

        from app.services.automation_engine import claim_action

        assert claim_action(orbity_db, org, act["id"]) is True
        assert claim_action(orbity_db, org, act["id"]) is False
    finally:
        orbity_db.table("automation_flows").delete().eq("id", flow["id"]).execute()
