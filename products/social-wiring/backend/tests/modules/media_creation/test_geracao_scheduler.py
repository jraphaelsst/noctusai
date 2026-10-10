"""Geração stale + dead-letter sweeps."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import anyio
import pytest

from noctusai_lib.domain.jobs import DeadLetterError, FakeJobRepository

from app.modules.media_creation import geracao_scheduler as sched
from app.modules.media_creation.services import geracao_jobs as gj

ORG = "test-org-123"
NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
CFG = SimpleNamespace(geracao_poll_seconds=0.01, geracao_lease_seconds=30.0)


def _ago(minutes: int) -> str:
    return (NOW - timedelta(minutes=minutes)).isoformat()


@pytest.fixture(autouse=True)
def _clean_registry():
    gj.clear_handlers()
    yield
    gj.clear_handlers()


def _by_id(sb, table):
    return {r["id"]: r for r in sb.from_(table).select("*").execute().data}


def _lote(sb, status, updated, origem="form_me"):
    lid = str(uuid.uuid4())
    sb.from_("cs_headline_lotes").insert({
        "id": lid, "org_id": ORG, "marca_id": str(uuid.uuid4()), "origem": origem,
        "status": status, "updated_at": updated,
    }).execute()
    return lid


class TestSweepStale:
    def test_only_stale_active_rows_fail(self, client):
        sb = client.mock_supabase
        old, fresh = _lote(sb, "processando", _ago(16)), _lote(sb, "processando", _ago(3))
        old_criando, done = _lote(sb, "criando", _ago(40)), _lote(sb, "completo", _ago(400))

        moved = sched.sweep_stale(sb, now=NOW)

        rows = _by_id(sb, "cs_headline_lotes")
        assert moved["lotes"] == 2
        assert rows[old]["status"] == rows[old_criando]["status"] == "falha"
        assert rows[old]["erro"] == "Tempo esgotado — tente novamente."
        assert rows[fresh]["status"] == "processando" and rows[done]["status"] == "completo"

    def test_roteiro_waiting_for_the_user_is_never_stale(self, client):
        sb = client.mock_supabase
        ids = {}
        for status in ("perguntas", "processando", "completo"):
            rid = str(uuid.uuid4())
            ids[status] = rid
            sb.from_("cs_roteiros").insert({
                "id": rid, "org_id": ORG, "marca_id": str(uuid.uuid4()), "status": status, "updated_at": _ago(120),
            }).execute()

        moved = sched.sweep_stale(sb, now=NOW)

        rows = _by_id(sb, "cs_roteiros")
        assert moved["roteiros"] == 1
        assert rows[ids["processando"]]["status"] == "falha"
        assert rows[ids["perguntas"]]["status"] == "perguntas" and rows[ids["completo"]]["status"] == "completo"

    def test_stale_classification_fails(self, client):
        sb = client.mock_supabase
        old, fresh = str(uuid.uuid4()), str(uuid.uuid4())
        for vid, upd in ((old, _ago(20)), (fresh, _ago(2))):
            sb.from_("cs_virais").insert({
                "id": vid, "org_id": ORG, "perfil_id": str(uuid.uuid4()),
                "classificacao_status": "processando", "updated_at": upd,
            }).execute()

        moved = sched.sweep_stale(sb, now=NOW)

        rows = _by_id(sb, "cs_virais")
        assert moved["virais"] == 1
        assert rows[old]["classificacao_status"] == "falhou"
        assert rows[fresh]["classificacao_status"] == "processando"


class TestSweepDeadLetters:
    def test_calls_the_owner_reconciler_for_each_dead_lettered_job(self, client):
        sb = client.mock_supabase
        lote = _lote(sb, "processando", _ago(1))

        def reconcile(db, job):
            db.from_("cs_headline_lotes").update({"status": "falha", "erro": sched.MSG_JOB_FAILED}).eq(
                "id", job.payload["lote_id"]
            ).execute()

        async def handler(job):
            raise DeadLetterError("sem estruturas")

        gj.register_handler("headline.gerar", handler, on_dead_letter=reconcile)

        async def go():
            repo = FakeJobRepository()
            await repo.enqueue(type="headline.gerar", payload={"lote_id": lote})
            await gj.build_geracao_worker(repo, CFG).run_once()
            return await sched.sweep_dead_letters(sb, repo)

        assert anyio.run(go) == 1
        assert _by_id(sb, "cs_headline_lotes")[lote]["status"] == "falha"

    def test_a_raising_reconciler_does_not_stop_the_sweep(self, client):
        calls: list = []

        def boom(db, job):
            calls.append(job.id)
            raise RuntimeError("row gone")

        async def handler(job):
            raise DeadLetterError("x")

        gj.register_handler("roteiro.gerar", handler, on_dead_letter=boom)

        async def go():
            repo = FakeJobRepository()
            for _ in range(2):
                await repo.enqueue(type="roteiro.gerar", payload={})
            worker = gj.build_geracao_worker(repo, CFG)
            await worker.run_once()
            await worker.run_once()
            return await sched.sweep_dead_letters(client.mock_supabase, repo)

        assert anyio.run(go) == 0 and len(calls) == 2


class TestSweepStranded:
    def test_never_raises_and_runs_the_sweeps(self, client):
        sb = client.mock_supabase
        lote = _lote(sb, "criando", (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat())

        anyio.run(lambda: sched.sweep_stranded(client=lambda: sb, repo=FakeJobRepository()))
        assert _by_id(sb, "cs_headline_lotes")[lote]["status"] == "falha"

        def explode():
            raise RuntimeError("db down")

        anyio.run(lambda: sched.sweep_stranded(client=explode))  # swallowed + logged

    def test_job_is_registered_on_a_free_minute_set(self):
        assert sched.JOB_ID == "geracao_stale_sweep"
        minutes = {int(m) for m in sched.CRON.split()[0].split(",")}
        from app.modules.media_creation import cerebro_scheduler

        assert minutes.isdisjoint({int(m) for m in cerebro_scheduler.CRON.split()[0].split(",")})
        assert minutes.isdisjoint({0, 5, 10, 15, 17, 20, 25, 30, 35, 40, 43, 45, 50, 55})
