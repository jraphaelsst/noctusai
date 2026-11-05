"""Vista imóveis refresh job — registration, discovery (orgs with a Vista credential), overdue arithmetic, catch-up.

Pins what makes the job work or silently not:

  · It registers as an INTERVAL job (default 7200 s, configurable) with an hour of misfire grace.
  · Candidates are the orgs holding a Vista credential record; discovery paginates past the 1000-row PostgREST cap.
  · An org with no credential is skipped (logged); one org failing never costs the others their refresh.
  · The startup catch-up refreshes orgs older than one interval and stays quiet otherwise.
  · Interval path and catch-up never overlap in one process; a lost per-org lease skips that org.
Drives the REAL entry points through the `_run` kwarg seams (no module patching) against a MockSupabaseClient admin.
"""
from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from noctusai_lib.testing import MockSupabaseClient

from app.services import imoveis_sync_scheduler as sched

_ORG_A = "6dd73140-74a4-41c6-aeff-bc94b5312b53"
_ORG_B = "0f5b1a2c-9d3e-4a7b-8c1d-2e3f4a5b6c7d"


class _Db(MockSupabaseClient):
    """`MockSupabaseClient.schema()` hands back a DIFFERENT client (data set on the root is invisible through it);
    the product code always goes through `.schema("social_wiring")`, so the schema is a no-op here."""

    def schema(self, _name):
        return self


class _Svc:
    """A sync service double with the two entry points `executar` uses."""

    chamadas: list = []

    def __init__(self, vazio: bool = False):
        self._vazio = vazio

    def _rel(self, caminho):
        return MagicMock(
            status_final="ok", complete=True,
            as_dict=lambda: {"caminho": caminho, "status": "ok", "novos": 0, "atualizados": 1}, chamadas={},
        )

    async def sync(self, org_id, *a, **k):
        _Svc.chamadas.append(("sync", str(org_id)))
        return self._rel("listar")

    async def sync_detalhes(self, org_id, *a, **k):
        _Svc.chamadas.append(("sync_detalhes", str(org_id)))
        return self._rel("detalhes")


def _factory(client, adapter, **kw):
    return _Svc()


@pytest.fixture(autouse=True)
def _limpa():
    _Svc.chamadas = []
    yield


@contextlib.contextmanager
def _lease_ok(_admin, _name, **_kw):
    yield True


@contextlib.contextmanager
def _lease_negado(_admin, _name, **_kw):
    yield False


def _admin():
    db = _Db()
    db.set_table_data("imoveis_sync_execucoes", [])
    return db


def _seams(admin, **over):
    base = dict(
        admin_factory=lambda: admin, adapter_factory=lambda _org: MagicMock(), discover_fn=lambda _a: [_ORG_A],
        sync_service_factory=_factory, lease_fn=_lease_ok, core_factory=lambda: None,
    )
    base.update(over)
    return base


# ─── Registration ───────────────────────────────────────────────────────


def test_configure_registers_an_interval_job_of_two_hours_by_default():
    from noctusai_lib.api import scheduler as seed_scheduler

    seed_scheduler.reset_for_testing()
    sched.configure()

    job = seed_scheduler.scheduler.get_job("imoveis_vista_refresh")
    assert job is not None, "job did not register — the mirror would never refresh"
    assert job.trigger.interval == timedelta(seconds=7200)


def test_configure_sets_an_hour_of_misfire_grace():
    from noctusai_lib.api import scheduler as seed_scheduler

    seed_scheduler.reset_for_testing()
    sched.configure()
    assert seed_scheduler.scheduler.get_job("imoveis_vista_refresh").misfire_grace_time == 3600


def test_configure_is_idempotent():
    from noctusai_lib.api import scheduler as seed_scheduler

    seed_scheduler.reset_for_testing()
    sched.configure()
    sched.configure()
    assert len(seed_scheduler.scheduler.get_jobs()) == 1


# ─── Overdue arithmetic ─────────────────────────────────────────────────


def _agora():
    return datetime.now(tz=timezone.utc)


def test_the_expected_slot_is_one_interval_ago():
    now = _agora()
    assert now - sched._last_expected_slot(now) == timedelta(seconds=7200)


def _com_ultimo(ts):
    db = _Db()
    db.set_table_data("imoveis", [{"org_id": _ORG_A, "sincronizado_em": ts}] if ts else [])
    return db


def test_org_refreshed_within_the_interval_is_not_overdue():
    now = _agora()
    assert sched._overdue_orgs(_com_ultimo((now - timedelta(minutes=30)).isoformat()), [_ORG_A], now) == []


def test_org_refreshed_before_the_interval_is_overdue():
    now = _agora()
    assert sched._overdue_orgs(_com_ultimo((now - timedelta(hours=5)).isoformat()), [_ORG_A], now) == [_ORG_A]


def test_org_never_synced_is_overdue():
    assert sched._overdue_orgs(_com_ultimo(None), [_ORG_A], _agora()) == [_ORG_A]


def test_unreadable_last_sync_counts_as_overdue():
    class _Quebrado:
        def schema(self, _n):
            raise RuntimeError("boom")

    assert sched._overdue_orgs(_Quebrado(), [_ORG_A], _agora()) == [_ORG_A]


# ─── Org discovery: those with a Vista credential ───────────────────────


def test_orgs_with_credential_are_the_provider_vista_rows_only_and_deduped():
    db = _Db()
    db.set_table_data("credentials", [
        {"org_id": _ORG_A, "provider": "vista"}, {"org_id": _ORG_B, "provider": "meta"},
        {"org_id": _ORG_B, "provider": "google_calendar"}, {"org_id": None, "provider": "vista"},
    ])
    assert sched._orgs_with_credential(db) == [_ORG_A]


def test_orgs_with_credential_paginates_past_the_postgrest_cap():
    db = _Db()
    db.set_table_data("credentials", [
        {"org_id": f"00000000-0000-4000-8000-{i:012d}", "provider": "vista"} for i in range(1500)
    ])
    assert len(sched._orgs_with_credential(db)) == 1500


# ─── The interval path ──────────────────────────────────────────────────


def test_an_org_without_a_vista_credential_is_skipped_and_the_others_still_run():
    admin = _admin()
    asyncio.run(sched.imoveis_vista_refresh_job(**_seams(
        admin, adapter_factory=lambda org: None if org == _ORG_A else MagicMock(), discover_fn=lambda _a: [_ORG_A, _ORG_B],
    )))
    assert _Svc.chamadas == [("sync", _ORG_B)]


def test_the_default_adapter_factory_is_per_org_and_refuses_without_a_record():
    from noctusai_lib.security.token_store import FakeCredentialStore

    from app.services import vista_credenciais

    vista_credenciais.configure_store(lambda: FakeCredentialStore())
    try:
        assert sched._build_adapter(_ORG_A) is None
    finally:
        vista_credenciais.configure_store(None)


def test_job_skips_when_no_org_has_a_credential():
    admin = _admin()
    asyncio.run(sched.imoveis_vista_refresh_job(**_seams(admin, discover_fn=lambda _a: [])))
    assert _Svc.chamadas == []


def test_interval_path_does_not_filter_by_overdue():
    called = MagicMock(return_value=[])
    asyncio.run(sched.imoveis_vista_refresh_job(**_seams(_admin(), overdue_fn=called, discover_fn=lambda _a: [_ORG_A, _ORG_B])))
    called.assert_not_called()
    assert len(_Svc.chamadas) == 2


def test_each_run_is_persisted_with_origin_and_scope():
    admin = _admin()
    asyncio.run(sched.imoveis_vista_refresh_job(**_seams(admin)))
    [row] = admin.schema("social_wiring").table("imoveis_sync_execucoes").select("*").execute().data
    assert row["org_id"] == _ORG_A and row["origem"] == "agendado" and row["modo"] == "auto" and row["status"] == "ok"
    assert row["escopo"] == "todos"  # no 'resto' pass yet today => this run also sweeps the rest
    assert row["relatorio"]["caminho"] == "listar"


def test_job_isolates_a_failing_org_and_still_runs_the_rest():
    class _Falha(_Svc):
        async def sync(self, org_id, *a, **k):
            if str(org_id) == _ORG_A:
                raise RuntimeError("boom")
            return await super().sync(org_id)

    asyncio.run(sched.imoveis_vista_refresh_job(**_seams(
        _admin(), sync_service_factory=lambda c, a, **k: _Falha(), discover_fn=lambda _a: [_ORG_A, _ORG_B],
    )))
    assert _Svc.chamadas == [("sync", _ORG_B)]


def test_job_survives_a_discovery_failure():
    def _boom(_a):
        raise RuntimeError("db down")

    asyncio.run(sched.imoveis_vista_refresh_job(**_seams(_admin(), discover_fn=_boom)))
    assert _Svc.chamadas == []


def test_a_lost_lease_skips_that_org():
    admin = _admin()
    asyncio.run(sched.imoveis_vista_refresh_job(**_seams(admin, lease_fn=_lease_negado)))
    assert _Svc.chamadas == []
    [row] = admin.schema("social_wiring").table("imoveis_sync_execucoes").select("*").execute().data
    assert row["status"] == "ignorada"


def test_holding_the_lease_runs_the_refresh():
    asyncio.run(sched.imoveis_vista_refresh_job(**_seams(_admin())))
    assert _Svc.chamadas == [("sync", _ORG_A)]


# ─── The catch-up path ──────────────────────────────────────────────────


def test_catch_up_runs_overdue_orgs():
    asyncio.run(sched.catch_up_if_overdue(**_seams(_admin(), overdue_fn=lambda _a, orgs, _now: orgs)))
    assert _Svc.chamadas == [("sync", _ORG_A)]


def test_catch_up_is_a_no_op_when_nothing_is_overdue():
    asyncio.run(sched.catch_up_if_overdue(**_seams(_admin(), overdue_fn=lambda _a, _o, _n: [])))
    assert _Svc.chamadas == []


def test_catch_up_refreshes_only_the_overdue_org():
    asyncio.run(sched.catch_up_if_overdue(**_seams(
        _admin(), discover_fn=lambda _a: [_ORG_A, _ORG_B], overdue_fn=lambda _a, _orgs, _now: [_ORG_B],
    )))
    assert _Svc.chamadas == [("sync", _ORG_B)]


def test_schedule_catch_up_returns_a_task_and_does_not_block():
    """Lifespan must not await a long refresh."""
    started = asyncio.Event()

    async def _slow():
        started.set()
        await asyncio.sleep(0)

    async def _drive():
        import app.services.imoveis_sync_scheduler as m
        original = m.catch_up_if_overdue
        m.catch_up_if_overdue = _slow
        try:
            task = m.schedule_catch_up()
            assert task is not None
            assert not task.done(), "schedule_catch_up blocked on the sync"
            await task
            assert started.is_set()
        finally:
            m.catch_up_if_overdue = original

    asyncio.run(_drive())


def test_schedule_catch_up_outside_a_loop_reports_rather_than_crashing(caplog):
    with caplog.at_level("ERROR"):
        assert sched.schedule_catch_up() is None
    assert any("did NOT start" in r.message for r in caplog.records)


def test_interval_and_catch_up_cannot_run_concurrently():
    concurrent = 0
    peak = 0

    class _Lento(_Svc):
        async def sync(self, org_id, *a, **k):
            nonlocal concurrent, peak
            concurrent += 1
            peak = max(peak, concurrent)
            await asyncio.sleep(0)
            concurrent -= 1
            return await super().sync(org_id)

    seams = _seams(_admin(), overdue_fn=lambda _a, orgs, _now: orgs, sync_service_factory=lambda c, a, **k: _Lento())

    async def _both():
        await asyncio.gather(sched.imoveis_vista_refresh_job(**seams), sched.catch_up_if_overdue(**seams))

    asyncio.run(_both())
    assert peak == 1, f"two refreshes overlapped (peak={peak})"
