"""The transcription job handler + worker (transcription-contract.md section 2)."""
from __future__ import annotations

from types import SimpleNamespace

import anyio
import pytest
from noctusai_lib.domain.jobs import JobStatus
from noctusai_lib.integrations.transcription import (
    FakeTranscriber,
    TranscriberBusy,
    TranscriberUnavailable,
    TranscriptionRejected,
)

from app.modules.transcricoes import hooks
from app.modules.transcricoes.deps import BUCKET
from app.modules.transcricoes.worker import RETRY_POLICY, build_worker
from tests.modules.transcricoes.conftest import AUDIO, probe
from tests.modules.transcricoes.test_submit_api import CTX, post, rows

CFG = SimpleNamespace(transcricao_gate_ttl_seconds=0.0, transcricao_poll_seconds=0.01, transcricao_lease_seconds=60.0)


class Recorder:
    def __init__(self):
        self.applied: list[dict] = []
        self.fail_next = 0

    def aplicar(self, db, row):
        if self.fail_next:
            self.fail_next -= 1
            raise RuntimeError("hook boom")
        self.applied.append(row)


@pytest.fixture
def hook():
    rec = Recorder()
    hooks.register_contexto(CTX, validar=lambda *a: None, aplicar=rec.aplicar)
    return rec


def make_worker(c, *, switch=lambda: True):
    return build_worker(c.jobs, c.mock_supabase, c.storage, CFG, lambda: c.transcriber, switch)


def run_once(worker):
    return anyio.run(worker.run_once)


def submit(c):
    r = post(c)
    assert r.status_code == 202, r.text
    return r.json()["data"]["id"]


def row_of(c, rid):
    return next(r for r in rows(c) if r["id"] == rid)


def blob(c, rid):
    key = row_of(c, rid)["storage_path"]
    return anyio.run(lambda: c.storage.get(bucket=BUCKET, key=key))


def only_job(c):
    return next(iter(c.jobs._jobs.values()))


def make_due(c):
    """Skip the backoff / reschedule wait: the queue row is claimable now."""
    job = only_job(c)
    c.jobs._jobs[job.id] = type(job)(**{**job.__dict__, "scheduled_for": None})


class TestSuccess:
    def test_text_saved_audio_deleted_hook_applied_once(self, client, hook):
        client.transcriber = FakeTranscriber(script=["olá mundo"], default_probe=probe(30.0))
        rid = submit(client)
        assert run_once(make_worker(client)) is True
        row = row_of(client, rid)
        assert row["status"] == "concluida" and row["texto"] == "olá mundo"
        assert row["concluido_em"] and row["iniciado_em"] and row["modelo"] == "fake"
        assert row["audio_apagado_em"] and blob(client, rid) is None
        assert row["hook_aplicado_em"] and len(hook.applied) == 1
        assert hook.applied[0]["texto"] == "olá mundo"
        assert only_job(client).status == JobStatus.COMPLETED
        assert client.transcriber.calls[0]["language"] == "pt"

    def test_rerun_of_a_finished_job_is_idempotent(self, client, hook):
        rid = submit(client)
        worker = make_worker(client)
        run_once(worker)
        n_calls = len(client.transcriber.calls)
        # the same job id re-delivered (lease reclaimed after a crash)
        job = only_job(client)
        anyio.run(lambda: worker._handlers["transcricao"](job))
        assert len(client.transcriber.calls) == n_calls and len(hook.applied) == 1
        assert row_of(client, rid)["status"] == "concluida"

    def test_hook_failure_releases_the_claim_and_the_retry_applies_it(self, client, hook):
        hook.fail_next = 1
        rid = submit(client)
        worker = make_worker(client)
        run_once(worker)
        row = row_of(client, rid)
        assert row["status"] == "concluida" and row["hook_aplicado_em"] is None and hook.applied == []
        job = only_job(client)
        assert job.status == JobStatus.PENDING and job.retry_count == 1
        # retry: the text is already saved -> NO second transcription, only the hook
        make_due(client)
        job2 = anyio.run(lambda: client.jobs.claim_next(worker_id="w", job_types=["transcricao"]))
        n_calls = len(client.transcriber.calls)
        anyio.run(lambda: worker._handlers["transcricao"](job2))
        assert len(client.transcriber.calls) == n_calls and len(hook.applied) == 1
        assert row_of(client, rid)["hook_aplicado_em"]


class TestBusyReschedules:
    def test_busy_does_not_consume_a_retry(self, client, hook):
        client.transcriber = FakeTranscriber(script=[TranscriberBusy(17.0), "depois"])
        rid = submit(client)
        worker = make_worker(client)
        run_once(worker)
        job = only_job(client)
        assert job.status == JobStatus.PENDING and job.retry_count == 0
        assert job.scheduled_for is not None
        row = row_of(client, rid)
        assert row["status"] == "na_fila" and row["audio_apagado_em"] is None and blob(client, rid) is not None
        assert hook.applied == []
        # due again: run it (make the schedule due by clearing it)
        make_due(client)
        run_once(worker)
        assert row_of(client, rid)["status"] == "concluida" and row_of(client, rid)["texto"] == "depois"
        assert only_job(client).retry_count == 0

    def test_busy_forever_never_dead_letters(self, client, hook):
        client.transcriber = FakeTranscriber(script=[TranscriberBusy(1.0)] * 6)
        rid = submit(client)
        worker = make_worker(client)
        for _ in range(6):
            make_due(client)
            run_once(worker)
        assert only_job(client).status == JobStatus.PENDING and only_job(client).retry_count == 0
        assert row_of(client, rid)["status"] == "na_fila"


class TestFailures:
    def test_rejected_audio_fails_without_refund_and_dead_letters(self, client, hook):
        client.transcriber = FakeTranscriber(script=[TranscriptionRejected("audio_corrompido")])
        rid = submit(client)
        run_once(make_worker(client))
        row = row_of(client, rid)
        assert row["status"] == "falhou" and row["erro_codigo"] == "audio_corrompido"
        assert row["minutos_reembolsados"] is False
        assert only_job(client).status == JobStatus.DEAD_LETTER
        assert blob(client, rid) is not None  # kept for the 72 h retention sweep
        assert hook.applied == []

    def test_unavailable_retries_then_fails_refunded(self, client, hook):
        client.transcriber = FakeTranscriber(script=[TranscriberUnavailable("down")] * 3)
        rid = submit(client)
        worker = make_worker(client)
        for attempt in range(RETRY_POLICY.max_retries + 1):
            make_due(client)
            run_once(worker)
            if attempt < RETRY_POLICY.max_retries:
                assert row_of(client, rid)["status"] == "na_fila"  # shown as queued while it retries
                assert only_job(client).retry_count == attempt + 1
        row = row_of(client, rid)
        assert row["status"] == "falhou" and row["erro_codigo"] == "transcricao_indisponivel"
        assert row["minutos_reembolsados"] is True
        assert only_job(client).status == JobStatus.DEAD_LETTER

    def test_missing_audio_fails_refunded(self, client, hook):
        rid = submit(client)
        key = row_of(client, rid)["storage_path"]
        anyio.run(lambda: client.storage.delete(bucket=BUCKET, key=key))
        run_once(make_worker(client))
        row = row_of(client, rid)
        assert row["status"] == "falhou" and row["erro_codigo"] == "audio_ausente"
        assert row["minutos_reembolsados"] is True

    def test_cancelled_while_queued_is_a_noop(self, client, hook):
        rid = submit(client)
        assert client.delete(f"/api/transcricoes/{rid}").status_code == 200
        n_calls = len(client.transcriber.calls)
        run_once(make_worker(client))
        assert len(client.transcriber.calls) == n_calls
        assert row_of(client, rid)["status"] == "cancelada"
        assert only_job(client).status == JobStatus.COMPLETED


class TestKillSwitchGate:
    def test_off_leaves_jobs_pending_untouched(self, client, hook):
        rid = submit(client)
        worker = make_worker(client, switch=lambda: False)
        assert run_once(worker) is False
        assert only_job(client).status == JobStatus.PENDING
        assert row_of(client, rid)["status"] == "na_fila" and client.transcriber.calls == []

    def test_turning_it_on_resumes(self, client, hook):
        state = {"on": False}
        rid = submit(client)
        worker = make_worker(client, switch=lambda: state["on"])
        assert run_once(worker) is False
        state["on"] = True
        assert run_once(worker) is True
        assert row_of(client, rid)["status"] == "concluida"

    def test_unreadable_switch_fails_closed(self):
        from app.modules.transcricoes import deps

        def boom(key):
            raise RuntimeError("db down")

        assert deps.read_kill_switch(boom) is False

    def test_a_db_value_wins_over_nothing(self):
        from app.modules.transcricoes import deps

        assert deps.read_kill_switch(lambda key: "true") is True
        assert deps.read_kill_switch(lambda key: None) is False

    @pytest.mark.parametrize("value,expected", [(None, False), ("", False), ("false", False), ("0", False),
                                                ("true", True), ("1", True), ("SIM", True)])
    def test_default_off_and_truthy_parsing(self, value, expected, monkeypatch):
        from app.modules.transcricoes import deps

        monkeypatch.delenv("TRANSCRICAO_HABILITADA", raising=False)
        if value is not None:
            monkeypatch.setenv("TRANSCRICAO_HABILITADA", value)
        assert deps.read_kill_switch() is expected


class TestLifecycle:
    def test_disabled_by_the_hard_switch_does_not_start(self, client):
        from app.modules.transcricoes import worker as w

        cfg = SimpleNamespace(**{**CFG.__dict__, "transcricao_worker_enabled": False})
        assert anyio.run(lambda: w.start_worker(cfg)) is False and not w.is_running()

    def test_start_runs_the_loop_and_stop_ends_it(self, client, hook, monkeypatch):
        from app.modules.transcricoes import worker as w

        monkeypatch.delenv("TRANSCRICAO_HABILITADA", raising=False)  # default OFF

        cfg = SimpleNamespace(**{**CFG.__dict__, "transcricao_worker_enabled": True})
        rid = submit(client)

        async def scenario():
            started = await w.start_worker(
                cfg, db=client.mock_supabase, repo=client.jobs, storage=client.storage,
                transcriber_factory=lambda: client.transcriber,
            )
            assert started and w.is_running()
            # the kill switch is the platform setting (default OFF here: no row, no env) -> nothing claimed
            await anyio.sleep(0.15)
            await w.stop_worker()
            assert not w.is_running()

        anyio.run(scenario)
        assert row_of(client, rid)["status"] == "na_fila" and only_job(client).status == JobStatus.PENDING
