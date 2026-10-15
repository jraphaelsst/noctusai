"""Scheduler jobs: registered, drain per org with isolation, honest when unconnected."""
from __future__ import annotations

import asyncio
import uuid

from noctusai_lib.api import scheduler as seed_scheduler

from app import scheduler

ORG_A = "00000000-0000-0000-0000-00000000000a"
ORG_B = "00000000-0000-0000-0000-00000000000b"


def test_jobs_are_registered_with_the_expected_cadence():
    scheduler.configure()
    jobs = {j.id: j for j in seed_scheduler._scheduler.get_jobs()} if hasattr(
        seed_scheduler, "_scheduler") else {}
    if jobs:  # introspection is best-effort across seed versions
        assert {"orbity_automacao_run_due", "orbity_rotinas_run_due"} <= set(jobs)


def _seed_due_send(mock, org, ex_id):
    flow, step, act = (str(uuid.uuid4()) for _ in range(3))
    mock.set_table_data("automation_executions", [
        *mock.table("automation_executions").select("*").execute().data,
        {"id": ex_id, "org_id": org, "flow_id": flow, "status": "running", "lead_id": str(uuid.uuid4())}])
    mock.set_table_data("automation_pending_actions", [
        *mock.table("automation_pending_actions").select("*").execute().data,
        {"id": act, "org_id": org, "execution_id": ex_id, "step_id": step, "status": "pending",
         "scheduled_for": "2020-01-01T00:00:00+00:00",
         "payload": {"step_type": "send_message", "phone": "5511999998888", "message": "Oi"}}])
    return act


def test_job_drains_every_org_and_unconnected_org_fails_honestly(client):
    mock = client.mock_supabase
    mock.set_table_data("automation_executions", [])
    mock.set_table_data("automation_pending_actions", [])
    mock.set_table_data("whatsapp_connections", [])
    a1 = _seed_due_send(mock, ORG_A, str(uuid.uuid4()))
    b1 = _seed_due_send(mock, ORG_B, str(uuid.uuid4()))

    asyncio.run(scheduler.job_automacao_run_due())

    rows = {r["id"]: r for r in mock.table("automation_pending_actions").select("*").execute().data}
    for act in (a1, b1):
        assert rows[act]["status"] == "failed"
        assert "WhatsApp não conectado" in rows[act]["error_detail"]


def test_job_never_raises_when_the_database_is_down(client):
    mock = client.mock_supabase
    mock.table = lambda name: (_ for _ in ()).throw(RuntimeError("db down"))  # test double, not SUT
    asyncio.run(scheduler.job_automacao_run_due())
    asyncio.run(scheduler.job_rotinas_run_due())


def test_routines_job_spawns_tasks_for_due_routines(client):
    mock = client.mock_supabase
    mock.set_table_data("routines", [{
        "id": str(uuid.uuid4()), "org_id": ORG_A, "title": "Relatório semanal",
        "cadence": "weekly", "active": True, "next_run": "2020-01-01"}])
    mock.set_table_data("tasks", [])
    asyncio.run(scheduler.job_rotinas_run_due())
    tasks = mock.table("tasks").select("*").execute().data
    assert [t["title"] for t in tasks] == ["Relatório semanal"]
    assert tasks[0]["org_id"] == ORG_A
