"""The library transcription lane (geracao-contract 3.4): ``submit_sistema`` + the second
worker and its claim gate. Every external seam is a production DI seam (kill switch,
transcriber factory, health probe, job repo, storage); the SQL RPC is a test-local double of
migration 229's ``reservar_transcricao_biblioteca`` (the shared rpc_fakes registry belongs to
other slices)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import anyio
import pytest
from noctusai_lib.domain.jobs import JobStatus
from noctusai_lib.integrations.transcription import (
    FakeTranscriber,
    TranscriberBusy,
    TranscriberUnavailable,
)

from app.modules.transcricoes import biblioteca_worker, hooks
from app.modules.transcricoes.biblioteca_worker import TranscriberHealth, voz_ocupada
from app.modules.transcricoes.deps import BUCKET
from app.modules.transcricoes.errors import TranscricaoErro
from app.modules.transcricoes.service import (
    CONTEXTO_BIBLIOTECA,
    JOB_TYPE,
    JOB_TYPE_BIBLIOTECA,
    TranscricaoService,
)
from app.modules.transcricoes.worker import build_worker as build_voice_worker
from tests.modules.transcricoes.conftest import AUDIO, ORG, USER, probe

CFG = SimpleNamespace(transcricao_gate_ttl_seconds=0.0, transcricao_poll_seconds=0.01, transcricao_lease_seconds=60.0)
OWNER = "perfil-owner-1"


class TestStats:
    def test_queue_stats_count_library_jobs_too(self, lane):
        sistema(lane)
        stats = anyio.run(lambda: service(lane).stats())
        assert stats["queue_stats"]["pending"] == 1


class Recorder:
    def __init__(self):
        self.applied: list[dict] = []

    def aplicar(self, db, row):
        self.applied.append(row)


@pytest.fixture
def lane(client):
    rec = Recorder()

    def validar(db, org, user, ref):
        if ref == "alheio":
            raise TranscricaoErro("nao_encontrada")

    hooks.register_contexto(CONTEXTO_BIBLIOTECA, validar=validar, aplicar=rec.aplicar)
    client.recorder = rec
    client.transcriber = FakeTranscriber(default_probe=probe(60.0))
    return client


def service(c, **kw) -> TranscricaoService:
    return TranscricaoService(
        c.mock_supabase, ORG, USER, storage=c.storage, jobs=c.jobs,
        transcriber_factory=lambda: c.transcriber, kill_switch=lambda: c.habilitada, **kw,
    )


def seed_lib(c, *, status, dur=60.0, org=ORG):
    rid = str(uuid.uuid4())
    c.mock_supabase.from_("transcricoes").insert({
        "id": rid, "org_id": org, "user_id": OWNER, "contexto_tipo": CONTEXTO_BIBLIOTECA, "contexto_ref": "v",
        "storage_path": f"{org}/{OWNER}/{rid}.webm", "bytes": 10, "duracao_s": dur, "formato": "webm",
        "status": status, "criado_em": datetime.now(timezone.utc).isoformat(),
        "minutos_reembolsados": False, "audio_apagado_em": None, "origem": "biblioteca",
    }).execute()
    return rid


def sistema(c, data=AUDIO, ref="viral-1"):
    return anyio.run(lambda: service(c).submit_sistema(data, ref, user_id=OWNER))


def rows(c):
    return c.mock_supabase.from_("transcricoes").select("*").execute().data


def jobs_of(c, type_):
    return [j for j in c.jobs._jobs.values() if j.type == type_]


async def _ok() -> bool:
    return True


class TestSubmitSistema:
    def test_enqueues_the_library_job_type_and_stores_the_audio(self, lane):
        out = sistema(lane)
        assert out["status"] == "na_fila" and out["duracao_s"] == 60.0
        (job,) = jobs_of(lane, JOB_TYPE_BIBLIOTECA)
        assert job.payload == {"transcricao_id": out["id"]} and jobs_of(lane, JOB_TYPE) == []
        (row,) = rows(lane)
        assert row["origem"] == "biblioteca" and row["user_id"] == OWNER and row["contexto_tipo"] == CONTEXTO_BIBLIOTECA
        assert anyio.run(lambda: lane.storage.get(bucket=BUCKET, key=row["storage_path"])) is not None

    def test_validation_order_size_magic_hook_probe_before_any_reservation(self, lane):
        too_big = AUDIO + b"\x00" * (service(lane).limits.max_bytes + 1)
        for data, ref, codigo in (
            (too_big, "viral-1", "arquivo_grande"),
            (b"not audio at all" * 10, "viral-1", "formato_invalido"),
            (AUDIO, "alheio", "nao_encontrada"),
        ):
            with pytest.raises(TranscricaoErro) as e:
                sistema(lane, data, ref)
            assert e.value.codigo == codigo
        assert rows(lane) == [] and lane.transcriber.calls == []

    def test_a_probe_failure_never_reserves(self, lane):
        lane.transcriber = FakeTranscriber(script=[], default_probe=probe(99999.0))
        with pytest.raises(TranscricaoErro):
            sistema(lane)
        assert rows(lane) == []

    def test_reel_longer_than_180s_is_refused(self, lane):
        lane.transcriber = FakeTranscriber(default_probe=probe(181.0))
        with pytest.raises(TranscricaoErro) as e:
            sistema(lane)
        assert (e.value.codigo, e.value.status) == ("reel_longo", 422) and rows(lane) == []

    def test_library_queue_is_capped_at_5(self, lane):
        for _ in range(5):
            seed_lib(lane, status="na_fila")
        with pytest.raises(TranscricaoErro) as e:
            sistema(lane)
        assert (e.value.codigo, e.value.status) == ("fila_biblioteca_cheia", 503)
        assert jobs_of(lane, JOB_TYPE_BIBLIOTECA) == []

    def test_org_daily_budget_is_30_min(self, lane):
        seed_lib(lane, status="concluida", dur=1790.0)
        with pytest.raises(TranscricaoErro) as e:
            sistema(lane)
        assert (e.value.codigo, e.value.status) == ("cota_diaria_biblioteca_org", 429)

    def test_platform_daily_budget_is_60_min(self, lane):
        for i in range(2):
            seed_lib(lane, status="concluida", dur=1790.0, org=f"other-{i}")
        with pytest.raises(TranscricaoErro) as e:
            sistema(lane)
        assert (e.value.codigo, e.value.status) == ("capacidade_diaria_biblioteca", 503)

    def test_library_rows_never_count_against_a_voice_answer(self, lane):
        for _ in range(5):
            seed_lib(lane, status="na_fila", dur=900.0)
        lane.transcriber = FakeTranscriber(default_probe=probe(30.0))
        from tests.modules.transcricoes.test_submit_api import CTX, post

        hooks.register_contexto(CTX, validar=lambda *a: None, aplicar=lambda *a: None)

        r = post(lane)
        assert r.status_code == 202, r.text

    def test_enqueue_failure_releases_the_reservation_and_the_audio(self, lane):
        async def boom(**kw):
            raise RuntimeError("queue down")

        lane.jobs.enqueue = boom  # the Fake queue double, not product code
        with pytest.raises(TranscricaoErro) as e:
            sistema(lane)
        assert e.value.codigo == "transcricao_indisponivel"
        (row,) = rows(lane)
        assert row["status"] == "falhou" and row["minutos_reembolsados"] is True
        assert anyio.run(lambda: lane.storage.get(bucket=BUCKET, key=row["storage_path"])) is None


def make_worker(c, *, switch=lambda: True, health=None):
    return biblioteca_worker.build_worker(
        c.jobs, c.mock_supabase, c.storage, CFG, lambda: c.transcriber, switch,
        health=health or TranscriberHealth(_ok),
    )


def gate(worker) -> bool:
    return anyio.run(worker.claim_allowed)


def enqueue_voice(c, status_running=False):
    job = anyio.run(lambda: c.jobs.enqueue(type=JOB_TYPE, payload={"transcricao_id": "x"}, max_retries=2))
    if status_running:
        anyio.run(lambda: c.jobs.claim_next(worker_id="voice", job_types=[JOB_TYPE]))
    return job


class TestClaimGate:
    def test_open_when_enabled_idle_and_healthy(self, lane):
        assert gate(make_worker(lane)) is True

    def test_closed_while_the_kill_switch_is_off(self, lane):
        assert gate(make_worker(lane, switch=lambda: False)) is False

    def test_closed_while_a_voice_job_is_pending_due(self, lane):
        enqueue_voice(lane)
        assert gate(make_worker(lane)) is False
        assert anyio.run(lambda: voz_ocupada(lane.jobs)) is True

    def test_closed_while_a_voice_job_is_running(self, lane):
        enqueue_voice(lane, status_running=True)
        assert gate(make_worker(lane)) is False

    def test_library_jobs_do_not_close_their_own_gate(self, lane):
        anyio.run(lambda: lane.jobs.enqueue(type=JOB_TYPE_BIBLIOTECA, payload={"transcricao_id": "x"}, max_retries=2))
        assert gate(make_worker(lane)) is True

    def test_closed_while_healthz_is_not_ok(self, lane):
        async def down() -> bool:
            return False

        assert gate(make_worker(lane, health=TranscriberHealth(down))) is False

    def test_healthz_is_cached_for_a_few_seconds(self, lane):
        calls = []
        now = [0.0]

        async def counted() -> bool:
            calls.append(1)
            return True

        health = TranscriberHealth(counted, ttl_s=5.0, clock=lambda: now[0])
        worker = make_worker(lane, health=health)
        assert gate(worker) and gate(worker) and len(calls) == 1
        now[0] = 6.0
        assert gate(worker) and len(calls) == 2

    def test_breaker_closes_after_consecutive_unavailable_and_half_opens_after_cooldown(self, lane):
        now = [0.0]
        health = TranscriberHealth(_ok, streak=3, cooldown_s=60.0, clock=lambda: now[0])
        for _ in range(2):
            health.record(unavailable=True)
        assert anyio.run(health.healthy) is True
        health.record(unavailable=True)
        assert anyio.run(health.healthy) is False
        now[0] = 61.0
        assert anyio.run(health.healthy) is True  # half-open: one call goes through
        health.record(unavailable=True)  # ... and fails again: closed at once
        assert anyio.run(health.healthy) is False

    def test_a_success_resets_the_streak(self, lane):
        health = TranscriberHealth(_ok, streak=3)
        health.record(unavailable=True)
        health.record(unavailable=True)
        health.record(unavailable=False)
        health.record(unavailable=True)
        assert anyio.run(health.healthy) is True


class TestWorker:
    def test_transcribes_deletes_audio_and_applies_the_hook(self, lane):
        lane.transcriber = FakeTranscriber(script=["texto do reel"], default_probe=probe(60.0))
        out = sistema(lane)
        assert anyio.run(make_worker(lane).run_once) is True
        (row,) = rows(lane)
        assert row["status"] == "concluida" and row["texto"] == "texto do reel"
        assert row["audio_apagado_em"] and anyio.run(lambda: lane.storage.get(bucket=BUCKET, key=row["storage_path"])) is None
        assert len(lane.recorder.applied) == 1 and lane.recorder.applied[0]["id"] == out["id"]
        assert jobs_of(lane, JOB_TYPE_BIBLIOTECA)[0].status == JobStatus.COMPLETED

    def test_busy_reschedules_without_consuming_a_retry(self, lane):
        lane.transcriber = FakeTranscriber(script=[TranscriberBusy(17.0), "depois"], default_probe=probe(60.0))
        sistema(lane)
        worker = make_worker(lane)
        anyio.run(worker.run_once)
        (job,) = jobs_of(lane, JOB_TYPE_BIBLIOTECA)
        assert job.status == JobStatus.PENDING and job.retry_count == 0 and job.scheduled_for is not None
        assert rows(lane)[0]["status"] == "na_fila"

    def test_unavailable_streak_closes_the_gate_so_retries_are_not_burned(self, lane):
        lane.transcriber = FakeTranscriber(script=[TranscriberUnavailable("down")] * 9, default_probe=probe(60.0))
        for _ in range(3):
            sistema(lane)
        health = TranscriberHealth(_ok, streak=2, cooldown_s=3600.0)
        worker = make_worker(lane, health=health)
        for _ in range(2):
            anyio.run(worker.run_once)
        # two reels hit the outage; the third is NOT claimed (the gate is closed)
        assert anyio.run(worker.run_once) is False
        assert sorted(j.retry_count for j in jobs_of(lane, JOB_TYPE_BIBLIOTECA)) == [0, 1, 1]

    def test_the_two_workers_never_claim_each_others_types(self, lane):
        sistema(lane)
        voice = build_voice_worker(lane.jobs, lane.mock_supabase, lane.storage, CFG, lambda: lane.transcriber, lambda: True)
        assert anyio.run(voice.run_once) is False
        assert jobs_of(lane, JOB_TYPE_BIBLIOTECA)[0].status == JobStatus.PENDING
        enqueue_voice(lane)
        assert anyio.run(make_worker(lane).run_once) is False  # gate closed, and not its type anyway
