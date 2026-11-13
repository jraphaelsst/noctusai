"""Run lifecycle (trigger -> draft -> approve/reject -> routine), dispatcher reconcile, daily report."""
from __future__ import annotations

from uuid import uuid4

import pytest

from noctusai_lib.domain.digest.types import DigestWindow
from noctusai_lib.domain.editorial import EditorialDenied, FakeEditorialStore
from noctusai_lib.domain.routines import (
    FakeRoutineStore,
    FakeSchedulerPort,
    RoutineBlocked,
    RoutineDispatcher,
    RoutineService,
    RoutinesDailyReport,
    RunItem,
)
from noctusai_lib.domain.routines.dispatcher import job_name
from noctusai_lib.domain.routines.workflow import ADMIN_GRANTS, ROUTINES_WORKFLOW

ORG, OWNER = uuid4(), uuid4()
CRON = "0 7 * * *"


class Collector:
    def __init__(self, items=(), boom=None):
        self.items, self.boom, self.calls = list(items), boom, 0

    async def collect(self, routine):
        self.calls += 1
        if self.boom:
            raise self.boom
        return self.items


def _setup(items=(("u1", {"t": "one"}), ("u2", {"t": "two"})), mode="trigger", enabled=True, boom=None):
    store, ed = FakeRoutineStore(), FakeEditorialStore(ROUTINES_WORKFLOW)
    col = Collector([RunItem(r, c) for r, c in items], boom)
    svc = RoutineService(store, ed, col)
    r = store.create_routine(org_id=ORG, name="news", cron=CRON, mode=mode, config={}, actor_id=OWNER)
    if enabled:
        store.set_enabled(org_id=ORG, routine_id=r.id, enabled=True, actor_id=OWNER, reason="go")
    return store, ed, col, svc, r


def _kinds(store):
    return [e.kind for e in store.list_events(ORG)]


@pytest.mark.asyncio
async def test_trigger_run_makes_drafts_awaiting_approval_and_events():
    store, ed, _, svc, r = _setup()
    res = await svc.run(ORG, r.id, actor_id=OWNER)
    assert (res.status, res.collected, res.drafts, res.published, res.duplicates) == ("ok", 2, 2, 0, 0)
    assert {i.state for i in ed.list_items(ORG)} == {"revisao_editorial"}
    ks = _kinds(store)
    assert ks[2:] == ["run_started", "draft_created", "draft_created", "run_finished"]
    started = store.list_events(ORG)[2]
    assert started.actor_id == OWNER and started.detail["source"] == "manual"


@pytest.mark.asyncio
async def test_rerun_dedups_on_ref():
    store, ed, _, svc, r = _setup()
    await svc.run(ORG, r.id, actor_id=OWNER)
    res = await svc.run(ORG, r.id, actor_id=OWNER)
    assert (res.drafts, res.duplicates) == (0, 2) and len(ed.list_items(ORG)) == 2


@pytest.mark.asyncio
async def test_routine_mode_publishes_automatically_as_system():
    store, ed, _, svc, r = _setup(mode="routine")
    res = await svc.run(ORG, r.id, scheduled=True)
    assert (res.drafts, res.published) == (2, 2)
    assert {i.state for i in ed.list_items(ORG)} == {"publicado"}
    approved = [e for e in store.list_events(ORG) if e.kind == "approved"]
    assert len(approved) == 2 and all(e.detail["auto"] for e in approved)


@pytest.mark.asyncio
async def test_approve_and_reject_one_step_with_events():
    store, ed, _, svc, r = _setup()
    res = await svc.run(ORG, r.id, actor_id=OWNER)
    a, b = res.item_ids
    svc.approve(ORG, r.id, a, actor_id=OWNER, grants=ADMIN_GRANTS)
    assert ed.get_item(ORG, a).state == "publicado"
    with pytest.raises(EditorialDenied) as e:
        svc.reject(ORG, r.id, b, actor_id=OWNER, grants=ADMIN_GRANTS, reason=" ")
    assert e.value.code == "motivo_required"
    svc.reject(ORG, r.id, b, actor_id=OWNER, grants=ADMIN_GRANTS, reason="off topic")
    assert ed.get_item(ORG, b).state == "arquivado"
    ev = [x for x in store.list_events(ORG) if x.kind in ("approved", "rejected")]
    assert [(x.kind, x.actor_id, x.reason) for x in ev] == [("approved", OWNER, None), ("rejected", OWNER, "off topic")]


@pytest.mark.asyncio
async def test_approve_requires_grant_and_rejects_foreign_item():
    store, ed, _, svc, r = _setup()
    other = store.create_routine(org_id=ORG, name="other", cron=CRON, mode="trigger", config={}, actor_id=OWNER)
    item = (await svc.run(ORG, r.id, actor_id=OWNER)).item_ids[0]
    with pytest.raises(EditorialDenied) as e:
        svc.approve(ORG, r.id, item, actor_id=OWNER, grants=[])
    assert e.value.code == "missing_grant"
    from noctusai_lib.domain.routines import RoutineNotFound

    with pytest.raises(RoutineNotFound):
        svc.approve(ORG, other.id, item, actor_id=OWNER, grants=ADMIN_GRANTS)


@pytest.mark.asyncio
async def test_gate_killed_master_off_and_disabled_never_run():
    store, _, col, svc, r = _setup()
    store.set_master(org_id=ORG, enabled=False, actor_id=OWNER, reason="incident")
    with pytest.raises(RoutineBlocked) as e:
        await svc.run(ORG, r.id, actor_id=OWNER)
    assert e.value.reason == "master_off"
    store.set_master(org_id=ORG, enabled=True, actor_id=OWNER, reason="ok")
    store.kill(org_id=ORG, routine_id=r.id, actor_id=OWNER, reason="bad")
    for scheduled in (False, True):
        with pytest.raises(RoutineBlocked) as e:
            await svc.run(ORG, r.id, scheduled=scheduled, actor_id=OWNER)
        assert e.value.reason == "killed"
    assert col.calls == 0 and "run_started" not in _kinds(store)


@pytest.mark.asyncio
async def test_disabled_blocks_scheduled_but_not_manual_trigger():
    store, _, _, svc, r = _setup(enabled=False)
    with pytest.raises(RoutineBlocked):
        await svc.run(ORG, r.id, scheduled=True)
    assert (await svc.run(ORG, r.id, actor_id=OWNER)).status == "ok"


@pytest.mark.asyncio
async def test_collector_error_records_run_finished_error_and_reraises():
    store, _, _, svc, r = _setup(boom=RuntimeError("source down"))
    with pytest.raises(RuntimeError):
        await svc.run(ORG, r.id, actor_id=OWNER)
    last = store.list_events(ORG)[-1]
    assert last.kind == "run_finished" and last.detail["status"] == "error" and "source down" in last.detail["error"]


# -- dispatcher ----------------------------------------------------------------------------------
def _disp(**kw):
    store, ed, col, svc, r = _setup(**kw)
    port = FakeSchedulerPort()
    return store, svc, port, RoutineDispatcher(store, svc, port), r


def test_reconcile_adds_updates_removes():
    store, _, port, d, r = _disp()
    res = d.reconcile()
    assert res.added == (job_name(r),) and port.jobs() == {job_name(r): CRON}
    assert d.reconcile().changed is False  # idempotent
    store.update_routine(org_id=ORG, routine_id=r.id, actor_id=OWNER, cron="5 5 * * *")
    assert d.reconcile().updated == (job_name(r),) and port.jobs()[job_name(r)] == "5 5 * * *"
    store.set_enabled(org_id=ORG, routine_id=r.id, enabled=False, actor_id=OWNER, reason="pause")
    assert d.reconcile().removed == (job_name(r),) and port.jobs() == {}


def test_reconcile_removes_on_kill_and_master_off_and_ignores_foreign_jobs():
    store, _, port, d, r = _disp()
    port.add("something-else", "* * * * *", lambda: None)
    d.reconcile()
    store.kill(org_id=ORG, routine_id=r.id, actor_id=OWNER, reason="bad")
    assert d.reconcile().removed == (job_name(r),)
    store.set_enabled(org_id=ORG, routine_id=r.id, enabled=True, actor_id=OWNER, reason="back")
    d.reconcile()
    store.set_master(org_id=ORG, enabled=False, actor_id=OWNER, reason="incident")
    assert d.reconcile().removed == (job_name(r),) and "something-else" in port.registered


@pytest.mark.asyncio
async def test_job_runs_the_service_and_a_killed_routine_skips_at_fire_time():
    from noctusai_lib.api.scheduler import SkipRun

    store, svc, port, d, r = _disp(mode="routine")
    d.reconcile()
    _, fn = port.registered[job_name(r)]
    await fn()
    assert "run_finished" in _kinds(store)
    store.kill(org_id=ORG, routine_id=r.id, actor_id=OWNER, reason="bad")  # between two reconciles
    with pytest.raises(SkipRun):
        await fn()


def test_ap_scheduler_port_registers_and_removes_on_the_seed_scheduler():
    from noctusai_lib.api import scheduler as sched
    from noctusai_lib.domain.routines import ApSchedulerPort

    sched.reset_for_testing()
    port, name = ApSchedulerPort(), f"routine:{ORG}:{uuid4()}"

    async def fn():
        return None

    port.add(name, CRON, fn)
    assert port.jobs() == {name: CRON}
    port.add(name, "1 1 * * *", fn)
    assert port.jobs() == {name: "1 1 * * *"}
    port.remove(name)
    assert port.jobs() == {}
    sched.reset_for_testing()


# -- daily report --------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_daily_report_counts_runs_errors_decisions_and_flags_kill_master():
    store, ed, _, svc, r = _setup()
    res = await svc.run(ORG, r.id, actor_id=OWNER)
    svc.approve(ORG, r.id, res.item_ids[0], actor_id=OWNER, grants=ADMIN_GRANTS)
    svc.reject(ORG, r.id, res.item_ids[1], actor_id=OWNER, grants=ADMIN_GRANTS, reason="off topic")
    store.kill(org_id=ORG, routine_id=r.id, actor_id=OWNER, reason="bad")
    store.set_master(org_id=ORG, enabled=False, actor_id=OWNER, reason="incident")
    out = await RoutinesDailyReport(client=store, org_id=str(ORG)).run(DigestWindow(period_days=1))
    row = out.summary["routines"][0]
    assert (row["runs"], row["drafts"], row["approved"], row["rejected"], row["killed"]) == (1, 2, 1, 1, True)
    assert row["rejections"] == ["off topic"]
    assert out.summary["master_enabled"] is False
    assert "DESLIGADA" in out.narrative and "MORTA" in out.narrative
    assert "off topic" in out.digest.text and out.digest.subject.startswith("Relatorio diario")
