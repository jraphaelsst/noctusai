"""Platform transcription API (CONTRACT products/core/projects/transcription-api).

Everything runs through the real seams with the seed Fakes: FakeTranscriber,
FakeJobRepository, FakeStorageBackend, FakeSessionStore/FakeApiTokenResolver,
the seed's real in-memory limiter, and the product ``FakeTranscricaoRepo``.
The runtime is handed to the router through ``dependency_overrides`` (the DI
seam) — nothing of ours is patched.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from noctusai_lib.api.auth.session import (
    AuthContext,
    FakeApiTokenResolver,
    FakeSessionStore,
)
from noctusai_lib.api.rate_limit import create_limiter
from noctusai_lib.domain.jobs import Job, JobStatus, make_job_repository
from noctusai_lib.integrations.storage import make_storage_backend
from noctusai_lib.integrations.transcription import (
    AudioProbe,
    FakeTranscriber,
    TranscriberBusy,
    TranscriberUnavailable,
    TranscriptionLimits,
    TranscriptionNotConfigured,
    TranscriptionRejected,
    TranscriptResult,
)
from noctusai_lib.testing import MockSupabaseClient

from app.routers import transcriptions as router_module
from app.services.transcription_api import limits as L
from app.services.transcription_api.auth import build_auth
from app.services.transcription_api.errors import CODIGOS, CODIGOS_RPC, TranscricaoErro, transcricao_erro_handler
from app.services.transcription_api.repository import FakeTranscricaoRepo, iso, parse_ts
from app.services.transcription_api.service import TranscricaoService
from app.services.transcription_api.wiring import TranscricaoRuntime, build_transcriber, get_runtime
from app.services.transcription_api.worker import TranscricaoBackground, TranscricaoFalha, TranscricaoJobHandler, run_sweeps

AUDIO = b"\x1a\x45\xdf\xa3" + b"A" * 200          # webm magic
AUDIO_2 = b"\x1a\x45\xdf\xa3" + b"B" * 300
ORG = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER = uuid.UUID("22222222-2222-2222-2222-222222222222")
ADMIN = uuid.UUID("33333333-3333-3333-3333-333333333333")
PROBE_OK = AudioProbe(duracao_s=30.0, codec="opus", container="webm", sample_rate=48000, canais=1)


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


class ProbeRejectingTranscriber(FakeTranscriber):
    """FakeTranscriber has no scripted probe failure; this is a test double,
    not a patch (the seed gap is reported in the delivery note)."""

    def __init__(self, error, **kw):
        super().__init__(**kw)
        self._error = error

    async def probe(self, audio):
        raise self._error


class Env:
    def __init__(self, *, max_bytes=None, transcriber=None, admin_role="admin", storage=None, get_transcriber=None):
        self.clock = Clock()
        self.flag = {"v": "true"}
        self.repo = FakeTranscricaoRepo(clock=self.clock)
        self.jobs = make_job_repository(use_fake=True)
        self.storage = storage or make_storage_backend(kind="fake")
        self.transcriber = transcriber or FakeTranscriber(default_probe=PROBE_OK)
        limits = L.build_limits(600)
        if max_bytes is not None:
            limits = TranscriptionLimits(max_bytes=max_bytes, max_duration_s=600.0)
        self.service = TranscricaoService(
            repo=self.repo, jobs=self.jobs, storage=self.storage,
            get_transcriber=get_transcriber or (lambda: self.transcriber),
            kill_switch=L.KillSwitch(lambda: self.flag["v"], ttl_s=0),
            limits=limits, clock=self.clock,
        )
        # seed auth Fakes through the real composition
        self.tokens = FakeApiTokenResolver()
        self.write_token = self._token("pk_write", ["transcription:write", "transcription:read"])
        self.other_token = self._token("pk_other", ["transcription:write", "transcription:read"])
        self.read_only = self._token("pk_ro", ["transcription:read"])
        self.write_only = self._token("pk_wo", ["transcription:write"])
        core = MockSupabaseClient()
        core.set_table_data("noctus_users", [{"id": str(ADMIN), "org_id": str(ORG), "org_role": "owner", "role": admin_role}])
        self.core = core

        async def legacy(token):
            uid = {"jwt-user": USER, "jwt-admin": ADMIN}.get(token)
            if uid is None:
                return None
            return AuthContext(org_id=ORG, caller_kind="user", user_id=uid, scopes=[], raw_token="s", api_token_id=None)

        self.auth = build_auth(
            session_store=FakeSessionStore(), api_token_resolver=self.tokens,
            legacy_jwt_resolver=legacy, get_core_client=lambda: self.core,
        )
        self.background = TranscricaoBackground(self.service, self.jobs)
        self.runtime = TranscricaoRuntime(
            service=self.service, auth=self.auth, burst=L.BurstLimiter(create_limiter()),
            background=self.background,
        )
        app = FastAPI()
        app.include_router(router_module.router)
        app.add_exception_handler(TranscricaoErro, transcricao_erro_handler)
        app.dependency_overrides[get_runtime] = lambda: self.runtime
        self.client = TestClient(app)

    def _token(self, secret, scopes):
        self.tokens.register(secret, org_id=ORG, scopes=scopes)
        return {"Authorization": f"Bearer {secret}"}

    def post(self, headers=None, data=AUDIO, **form):
        return self.client.post(
            "/api/transcriptions", headers=headers or self.write_token,
            files={"arquivo": ("voz original.webm", data, "audio/webm")}, data=form,
        )

    def work(self):
        return asyncio.run(self.background.worker.run_once())

    def handler(self):
        return TranscricaoJobHandler(
            self.service, clock=self.clock, retry_policy=self.background.worker._retry_policy
        )


@pytest.fixture
def env():
    return Env()


def _job(tid, retry_count=0):
    now = datetime.now(timezone.utc)
    return Job(
        id="j", type=L.JOB_TYPE, payload={"transcricao_id": tid}, status=JobStatus.RUNNING,
        retry_count=retry_count, max_retries=2, last_error=None, created_at=now, updated_at=now,
    )


# ── submit ──────────────────────────────────────────────────────────────────


def test_submit_202_happy_path(env):
    r = env.post(idioma="pt", rotulo="reuniao")
    assert r.status_code == 202
    body = r.json()
    assert set(body) == {"id", "status", "posicao", "estimativa_s", "duracao_s"}
    assert body["status"] == "na_fila" and body["posicao"] == 1 and body["duracao_s"] == 30.0
    row = env.repo.rows[body["id"]]
    assert row["caller_kind"] == "token" and row["org_id"] == str(ORG)
    assert row["rotulo"] == "reuniao" and row["formato"] == "webm" and row["bytes"] == len(AUDIO)
    # path is org/kind/caller/<id>.<ext> — the original filename is never stored
    assert "voz" not in row["storage_path"] and row["storage_path"].endswith(f"{body['id']}.webm")
    assert asyncio.run(env.storage.exists(bucket=L.BUCKET, key=row["storage_path"]))
    # job payload carries the id only
    stats = asyncio.run(env.jobs.queue_stats(job_types=[L.JOB_TYPE]))
    assert stats.pending == 1
    claimed = asyncio.run(env.jobs.claim_next(worker_id="t", job_types=[L.JOB_TYPE]))
    assert claimed.payload == {"transcricao_id": body["id"]}


def test_submit_as_user_session_is_allowed_and_identified_as_user(env):
    r = env.post(headers={"Authorization": "Bearer jwt-admin"})
    assert r.status_code == 202
    row = env.repo.rows[r.json()["id"]]
    assert (row["caller_kind"], row["caller_id"]) == ("user", str(ADMIN))


@pytest.mark.parametrize("method,path", [
    ("post", "/api/transcriptions"), ("get", "/api/transcriptions"),
    ("get", f"/api/transcriptions/{uuid.uuid4()}"), ("delete", f"/api/transcriptions/{uuid.uuid4()}"),
    ("get", "/api/transcriptions/_stats"),
])
def test_no_credential_is_strict_401(env, method, path):
    kwargs = {"files": {"arquivo": ("a.webm", AUDIO, "audio/webm")}} if method == "post" else {}
    assert getattr(env.client, method)(path, **kwargs).status_code == 401


def test_invalid_pk_token_is_strict_401(env):
    r = env.client.get("/api/transcriptions", headers={"Authorization": "Bearer pk_nope"})
    assert r.status_code == 401


def test_missing_scope_is_403_escopo_insuficiente(env):
    r = env.post(headers=env.read_only)
    assert r.status_code == 403 and r.json() == {
        "codigo": "escopo_insuficiente", "mensagem": CODIGOS["escopo_insuficiente"][1]}
    r = env.client.get("/api/transcriptions", headers=env.write_only)
    assert r.status_code == 403 and r.json()["codigo"] == "escopo_insuficiente"
    assert env.repo.reservas == []


def test_413_over_cap_and_nothing_reserved():
    env = Env(max_bytes=1024)
    r = env.post(data=b"\x1a\x45\xdf\xa3" + b"A" * 2000)
    assert r.status_code == 413 and r.json()["codigo"] == "arquivo_grande"
    assert env.repo.reservas == []


def test_415_unknown_magic_bytes(env):
    r = env.post(data=b"\x89PNG\r\n\x1a\n" + b"x" * 64)
    assert r.status_code == 415 and r.json()["codigo"] == "formato_invalido"
    assert env.repo.reservas == []


def test_415_probe_codec_not_allowed():
    env = Env(transcriber=FakeTranscriber(default_probe=AudioProbe(30.0, "vorbis", "webm")))
    r = env.post()
    assert r.status_code == 415 and r.json()["codigo"] == "formato_invalido"


@pytest.mark.parametrize("dur,codigo", [(700.0, "duracao_excedida"), (0.4, "audio_vazio")])
def test_422_probe_duration(dur, codigo):
    env = Env(transcriber=FakeTranscriber(default_probe=AudioProbe(dur, "opus", "webm")))
    r = env.post()
    assert r.status_code == 422 and r.json()["codigo"] == codigo
    assert env.repo.reservas == []  # quota is never charged for a refused file


def test_422_audio_corrompido_from_probe():
    env = Env(transcriber=ProbeRejectingTranscriber(TranscriptionRejected("audio_corrompido")))
    r = env.post()
    assert r.status_code == 422 and r.json()["codigo"] == "audio_corrompido"


def test_quota_is_charged_on_probed_duration(env):
    env.post()
    assert env.repo.reservas[0]["duracao_s"] == 30.0


@pytest.mark.parametrize("codigo", sorted(CODIGOS_RPC))
def test_every_rpc_codigo_is_mapped_with_retry_after(env, codigo):
    env.repo.script_reservar.append({"ok": False, "codigo": codigo, "retry_after_s": 42})
    r = env.post()
    assert r.status_code == CODIGOS[codigo][0] == (429 if codigo.startswith(("limite", "cota")) else 503)
    assert r.json()["codigo"] == codigo and r.headers["Retry-After"] == "42"
    assert env.storage._blobs == {}  # nothing stored, nothing queued
    assert asyncio.run(env.jobs.queue_stats()).pending == 0


def test_unknown_rpc_codigo_is_503_not_guessed(env):
    env.repo.script_reservar.append({"ok": False, "codigo": "inventado", "retry_after_s": 1})
    r = env.post()
    assert r.status_code == 503 and r.json()["codigo"] == "transcricao_indisponivel"
    assert "Retry-After" in r.headers


def test_503_kill_switch_off(env):
    env.flag["v"] = "false"
    r = env.post()
    assert r.status_code == 503 and r.json()["codigo"] == "transcricao_desativada"
    assert int(r.headers["Retry-After"]) >= 1
    assert env.repo.reservas == []


def test_503_transcriber_unavailable_on_probe():
    env = Env(transcriber=ProbeRejectingTranscriber(TranscriberUnavailable("down")))
    r = env.post()
    assert r.status_code == 503 and r.json()["codigo"] == "transcricao_indisponivel"
    assert "Retry-After" in r.headers and env.repo.reservas == []


def test_storage_failure_after_reservation_fails_and_refunds():
    async def boom(**kw):
        raise OSError("bucket exploded /secret/path")

    env = Env(storage=SimpleNamespace(put=boom))  # a failing StorageBackend, wired through the ctor seam
    r = env.post()
    assert r.status_code == 503 and r.json()["codigo"] == "transcricao_indisponivel"
    (row,) = env.repo.rows.values()
    assert row["status"] == "falhou" and row["erro_codigo"] == "armazenamento" and row["minutos_reembolsados"]


def test_burst_limit_per_identity_is_429_with_retry_after(env):
    for _ in range(10):
        assert env.post().status_code == 202
    r = env.post()
    assert r.status_code == 429 and r.json()["codigo"] == "limite_requisicoes"
    assert int(r.headers["Retry-After"]) >= 1
    # another identity has its own bucket
    assert env.post(headers=env.other_token).status_code == 202


# ── reads ───────────────────────────────────────────────────────────────────


def test_get_queued_has_position_and_no_text(env):
    tid = env.post().json()["id"]
    r = env.client.get(f"/api/transcriptions/{tid}", headers=env.write_token)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "na_fila" and body["posicao"] == 1 and "texto" not in body
    assert {"id", "duracao_s", "idioma", "criado_em", "expira_em"} <= set(body)


def test_cross_caller_is_404_never_403(env):
    tid = env.post().json()["id"]
    for method in ("get", "delete"):
        r = getattr(env.client, method)(f"/api/transcriptions/{tid}", headers=env.other_token)
        assert r.status_code == 404 and r.json()["codigo"] == "nao_encontrada"
    assert env.client.get("/api/transcriptions", headers=env.other_token).json() == {"items": []}
    assert env.repo.rows[tid]["status"] == "na_fila"  # the foreign DELETE changed nothing
    assert env.client.get("/api/transcriptions/not-a-uuid", headers=env.write_token).status_code == 404


def test_list_pagination_status_filter_and_no_text(env):
    ids = []
    for _ in range(3):
        env.clock.advance(seconds=1)
        ids.append(env.post().json()["id"])
    p1 = env.client.get("/api/transcriptions?limit=2", headers=env.write_token).json()
    assert [i["id"] for i in p1["items"]] == [ids[2], ids[1]] and "next_cursor" in p1
    p2 = env.client.get(f"/api/transcriptions?limit=2&cursor={p1['next_cursor']}", headers=env.write_token).json()
    assert [i["id"] for i in p2["items"]] == [ids[0]] and "next_cursor" not in p2
    assert all("texto" not in i and "segmentos" not in i for i in p1["items"])
    assert env.client.get("/api/transcriptions?status=concluida", headers=env.write_token).json()["items"] == []
    assert env.client.get("/api/transcriptions?status=bogus", headers=env.write_token).status_code == 415


# ── worker ──────────────────────────────────────────────────────────────────


def test_worker_completes_job_and_deletes_audio_immediately():
    env = Env(transcriber=FakeTranscriber(default_probe=PROBE_OK, script=["ola mundo"]))
    tid = env.post(segmentos="true").json()["id"]
    path = env.repo.rows[tid]["storage_path"]
    assert env.work() is True
    body = env.client.get(f"/api/transcriptions/{tid}", headers=env.write_token).json()
    assert body["status"] == "concluida" and body["texto"] == "ola mundo" and body["modelo"] == "fake"
    assert "segmentos" not in body or body["segmentos"] == []  # fake emits none
    assert body["expira_em"] == iso(parse_ts(body["concluido_em"]) + timedelta(days=30))
    assert not asyncio.run(env.storage.exists(bucket=L.BUCKET, key=path))
    assert env.repo.rows[tid]["audio_apagado_em"]
    assert env.transcriber.calls[0]["max_seconds"] == 30.0


def test_segments_only_stored_when_requested():
    class Seg(FakeTranscriber):
        async def transcribe(self, audio, *, language="pt", max_seconds):
            r = await super().transcribe(audio, language=language, max_seconds=max_seconds)
            return TranscriptResult(r.text, r.duracao_s, r.idioma, r.modelo, r.rtf, [{"start": 0, "end": 1, "text": "x"}])

    env = Env(transcriber=Seg(default_probe=PROBE_OK))
    with_seg = env.post(segmentos="true").json()["id"]
    without = env.post().json()["id"]
    env.work(); env.work()
    got = env.client.get(f"/api/transcriptions/{with_seg}", headers=env.write_token).json()
    assert got["segmentos"] == [{"start": 0, "end": 1, "text": "x"}]
    assert "segmentos" not in env.client.get(f"/api/transcriptions/{without}", headers=env.write_token).json()


def test_busy_reschedules_without_consuming_a_retry():
    env = Env(transcriber=FakeTranscriber(default_probe=PROBE_OK, script=[TranscriberBusy(7.0)]))
    tid = env.post().json()["id"]
    assert env.work() is True
    job = asyncio.run(env.jobs.claim_next(worker_id="probe", job_types=[L.JOB_TYPE]))
    assert job is None  # rescheduled into the future, not claimable now
    (stored,) = env.jobs._jobs.values()
    assert stored.status == JobStatus.PENDING and stored.retry_count == 0
    assert stored.scheduled_for is not None and stored.scheduled_for > datetime.now(timezone.utc)
    assert env.repo.rows[tid]["status"] == "na_fila" and not env.repo.rows[tid]["minutos_reembolsados"]


def test_unavailable_retries_then_fails_and_refunds():
    env = Env(transcriber=FakeTranscriber(
        default_probe=PROBE_OK, script=[TranscriberUnavailable("x")] * 3))
    tid = env.post().json()["id"]
    assert env.work() is True  # attempt 0
    (stored,) = env.jobs._jobs.values()
    assert stored.status == JobStatus.PENDING and stored.retry_count == 1
    assert env.repo.rows[tid]["status"] == "na_fila" and not env.repo.rows[tid]["minutos_reembolsados"]
    handler = env.handler()
    with pytest.raises(TranscricaoFalha):
        asyncio.run(handler(_job(tid, retry_count=2)))  # final attempt
    row = env.repo.rows[tid]
    assert row["status"] == "falhou" and row["erro_codigo"] == "transcricao_indisponivel"
    assert row["minutos_reembolsados"] is True
    body = env.client.get(f"/api/transcriptions/{tid}", headers=env.write_token).json()
    assert body["erro"]["codigo"] == "transcricao_indisponivel" and "texto" not in body


def test_rejected_audio_fails_without_refund():
    env = Env(transcriber=FakeTranscriber(default_probe=PROBE_OK, script=[FakeTranscriber.rejected("audio_corrompido")]))
    tid = env.post().json()["id"]
    env.work()
    row = env.repo.rows[tid]
    assert row["status"] == "falhou" and row["erro_codigo"] == "audio_corrompido"
    assert row["minutos_reembolsados"] is False
    (stored,) = env.jobs._jobs.values()
    assert stored.status == JobStatus.DEAD_LETTER


def test_result_write_is_idempotent():
    env = Env(transcriber=FakeTranscriber(default_probe=PROBE_OK, script=["primeiro", "segundo"]))
    tid = env.post().json()["id"]
    env.work()
    asyncio.run(env.handler()(_job(tid)))  # lease-reclaim re-run of the same job
    assert env.repo.rows[tid]["texto"] == "primeiro"
    assert len(env.transcriber.calls) == 1


def test_kill_switch_off_leaves_queued_jobs_untouched():
    env = Env()
    tid = env.post().json()["id"]
    env.flag["v"] = "false"
    assert env.work() is False
    assert env.repo.rows[tid]["status"] == "na_fila"
    assert asyncio.run(env.jobs.queue_stats()).pending == 1


def test_worker_uses_one_job_type_with_lease_and_retry_budget():
    env = Env()
    w = env.background.worker
    assert w._job_types == [L.JOB_TYPE] and w._lease_seconds == 300.0
    assert w._retry_policy.max_retries == 2


# ── DELETE ──────────────────────────────────────────────────────────────────


def test_delete_queued_cancels_refunds_and_deletes_audio(env):
    tid = env.post().json()["id"]
    path = env.repo.rows[tid]["storage_path"]
    r = env.client.delete(f"/api/transcriptions/{tid}", headers=env.write_token)
    assert r.status_code == 204 and r.content == b""
    row = env.repo.rows[tid]
    assert row["status"] == "cancelada" and row["minutos_reembolsados"] is True
    assert not asyncio.run(env.storage.exists(bucket=L.BUCKET, key=path))
    # the orphaned job is a no-op for the worker
    assert env.work() is True and env.transcriber.calls == []


def test_delete_processing_is_409_em_processamento(env):
    tid = env.post().json()["id"]
    env.repo.rows[tid]["status"] = "processando"
    r = env.client.delete(f"/api/transcriptions/{tid}", headers=env.write_token)
    assert r.status_code == 409 and r.json()["codigo"] == "em_processamento"
    assert env.repo.rows[tid]["status"] == "processando"


def test_delete_completed_purges_text_now():
    env = Env(transcriber=FakeTranscriber(default_probe=PROBE_OK, script=["texto longo"]))
    tid = env.post().json()["id"]
    env.work()
    assert env.client.delete(f"/api/transcriptions/{tid}", headers=env.write_token).status_code == 204
    assert env.repo.rows[tid]["texto"] is None and env.repo.rows[tid]["status"] == "concluida"


# ── stats ───────────────────────────────────────────────────────────────────


def test_stats_platform_admin_only():
    env = Env()
    env.post()
    r = env.client.get("/api/transcriptions/_stats", headers={"Authorization": "Bearer jwt-admin"})
    assert r.status_code == 200
    body = r.json()
    assert body["fila"] == 1 and body["processando"] == 0 and body["habilitada"] is True
    assert body["minutos_hoje_global"] == 0.5
    assert body["minutos_hoje_por_org"] == [{"org_id": str(ORG), "minutos": 0.5}]
    assert body["worker_saudavel"] is False  # background not started in this process
    # a token (no user identity) and a non-admin user are refused
    assert env.client.get("/api/transcriptions/_stats", headers=env.write_token).status_code == 403
    plain = Env(admin_role="user")
    r = plain.client.get("/api/transcriptions/_stats", headers={"Authorization": "Bearer jwt-admin"})
    assert r.status_code == 403 and r.json()["codigo"] == "escopo_insuficiente"


# ── retention sweeps ────────────────────────────────────────────────────────


def test_sweeps_audio_72h_text_30d_and_stuck_jobs():
    env = Env(transcriber=FakeTranscriber(default_probe=PROBE_OK, script=["x", FakeTranscriber.rejected()]))
    done = env.post().json()["id"]
    env.work()
    failed = env.post(data=AUDIO_2).json()["id"]
    env.work()
    stuck = env.post(data=AUDIO + b"C").json()["id"]
    assert env.repo.rows[failed]["status"] == "falhou"
    fpath = env.repo.rows[failed]["storage_path"]

    env.clock.advance(hours=71)
    out = asyncio.run(run_sweeps(env.service))
    assert out["audio_apagado"] == 0 and asyncio.run(env.storage.exists(bucket=L.BUCKET, key=fpath))
    assert out["travados"] == 1  # `stuck` never started and is past its 6 h deadline
    assert env.repo.rows[stuck]["status"] == "falhou" and env.repo.rows[stuck]["erro_codigo"] == "tempo_excedido"
    assert env.repo.rows[stuck]["minutos_reembolsados"] is True

    env.clock.advance(hours=2)  # `failed` is now 73 h old; `stuck` failed 2 h ago
    out = asyncio.run(run_sweeps(env.service))
    assert out["audio_apagado"] == 1
    assert not asyncio.run(env.storage.exists(bucket=L.BUCKET, key=fpath))
    assert env.repo.rows[failed]["audio_apagado_em"] and not env.repo.rows[stuck]["audio_apagado_em"]
    env.clock.advance(hours=71)  # `stuck` passes 72 h too
    assert asyncio.run(run_sweeps(env.service))["audio_apagado"] == 1

    assert env.repo.rows[done]["texto"] == "x"
    env.clock.advance(days=30)
    out = asyncio.run(run_sweeps(env.service))
    assert out["texto_purgado"] == 1 and env.repo.rows[done]["texto"] is None
    assert env.repo.rows[done]["status"] == "concluida"  # row stays for quota history
    assert asyncio.run(run_sweeps(env.service)) == {"audio_apagado": 0, "texto_purgado": 0, "travados": 0, "erros": 0}


def test_stuck_deadline_honours_started_job_formula():
    env = Env()
    tid = env.post().json()["id"]
    env.repo.rows[tid].update(status="processando", iniciado_em=iso(env.clock.now))
    env.clock.advance(hours=1, minutes=30)  # 3*30 s + 1 h = 1 h 1.5 min → exceeded
    assert asyncio.run(run_sweeps(env.service))["travados"] == 1
    assert env.repo.rows[tid]["status"] == "falhou"


# ── logging ─────────────────────────────────────────────────────────────────


def test_job_log_line_has_no_text_and_no_storage_path(caplog):
    secret = "TEXTO-SECRETO-DA-REUNIAO"
    env = Env(transcriber=FakeTranscriber(default_probe=PROBE_OK, script=[secret, TranscriberUnavailable("path /x/y.webm")]))
    caplog.set_level(logging.DEBUG)
    ok = env.post().json()["id"]
    env.work()
    bad = env.post(data=AUDIO_2).json()["id"]
    env.work()
    paths = [env.repo.rows[i]["storage_path"] for i in (ok, bad)]
    text = caplog.text
    assert secret not in text
    for p in paths:
        assert p not in text and ".webm" not in text
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("transcricao.job ")]
    assert len(lines) == 1  # one line for the finished job (the retry is logged without fields)
    for field in ("id=", "org=", "caller_kind=token", "bytes=", "duracao_s=30.0", "rtf=", "wait_s=", "status=concluida", "codigo="):
        assert field in lines[0]


# ── config / wiring ─────────────────────────────────────────────────────────


def test_local_whisper_without_url_or_token_raises_never_falls_back(monkeypatch):
    monkeypatch.delenv("TRANSCRIBER_URL", raising=False)
    monkeypatch.delenv("TRANSCRIBER_TOKEN", raising=False)
    s = SimpleNamespace(transcription_backend="local_whisper", transcriber_url="", transcriber_token="")
    with pytest.raises(TranscriptionNotConfigured):
        build_transcriber(s)
    with pytest.raises(TranscriptionNotConfigured):
        build_transcriber(SimpleNamespace(transcription_backend="", transcriber_url="", transcriber_token=""))


def test_local_whisper_takes_url_and_token_from_settings(monkeypatch):
    monkeypatch.setenv("TRANSCRIBER_URL", "")
    monkeypatch.setenv("TRANSCRIBER_TOKEN", "")
    s = SimpleNamespace(transcription_backend="local_whisper", transcriber_url="http://noctus-transcriber:9000", transcriber_token="tok")
    assert type(build_transcriber(s)).__name__ == "LocalWhisperTranscriber"


def test_misconfigured_transcriber_is_503_on_submit():
    def broken():
        raise TranscriptionNotConfigured("TRANSCRIPTION_BACKEND=local_whisper requires ...")

    env = Env(get_transcriber=broken)
    r = env.post()
    assert r.status_code == 503 and r.json()["codigo"] == "transcricao_indisponivel"


def test_core_app_registers_router_handler_and_upload_body_override():
    from app.main import app

    routes = {(m, r.path) for r in app.routes for m in getattr(r, "methods", ())}
    assert ("POST", "/api/transcriptions") in routes
    assert ("GET", "/api/transcriptions/_stats") in routes
    assert ("DELETE", "/api/transcriptions/{transcricao_id}") in routes
    assert TranscricaoErro in app.exception_handlers
    # `_stats` is declared before `/{transcricao_id}` so it is not shadowed
    paths = [r.path for r in app.routes if getattr(r, "path", "").startswith("/api/transcriptions")]
    assert paths.index("/api/transcriptions/_stats") < paths.index("/api/transcriptions/{transcricao_id}")


# ── Supabase repo against the seed MockSupabaseClient ───────────────────────


def test_supabase_repo_reservar_and_scoped_get():
    from app.services.transcription_api.repository import SupabaseTranscricaoRepo

    client = MockSupabaseClient()
    tid = str(uuid.uuid4())
    client.set_rpc_data("reservar_transcricao_api", {"ok": True, "id": tid})
    repo = SupabaseTranscricaoRepo(client)
    assert repo.reservar(caller_kind="token", caller_id=USER, org_id=ORG, duracao_s=30.0) == {"ok": True, "id": tid}
    name, params = client.rpc_calls[0]
    assert name == "reservar_transcricao_api"
    assert params == {"p_caller_kind": "token", "p_caller_id": str(USER), "p_org_id": str(ORG), "p_duracao_s": 30.0}
    client.set_table_data("transcricoes_api", [{"id": tid, "status": "na_fila", "caller_kind": "token", "caller_id": str(USER)}])
    assert repo.get_for_caller(tid, "token", USER)["id"] == tid
    client.set_rpc_data("reservar_transcricao_api", None)
    with pytest.raises(RuntimeError):
        repo.reservar(caller_kind="token", caller_id=USER, org_id=ORG, duracao_s=30.0)
