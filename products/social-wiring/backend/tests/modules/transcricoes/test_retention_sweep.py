"""Retention + safety-net sweep (transcription-contract.md section 3, LGPD)."""
from __future__ import annotations

from datetime import timedelta

import anyio

from app.modules.transcricoes import scheduler
from app.modules.transcricoes.deps import BUCKET
from tests.modules.transcricoes.test_submit_api import CTX, rows, seed  # noqa: F401


def put_audio(c, rid):
    row = next(r for r in rows(c) if r["id"] == rid)
    anyio.run(lambda: c.storage.put(bucket=BUCKET, key=row["storage_path"], data=b"x"))
    return row["storage_path"]


def has_audio(c, key):
    return anyio.run(lambda: c.storage.get(bucket=BUCKET, key=key)) is not None


def mark(c, rid, **patch):
    c.mock_supabase.from_("transcricoes").update(patch).eq("id", rid).execute()


def sweep(c):
    anyio.run(lambda: scheduler.run_sweep(db=lambda: c.mock_supabase, storage=lambda: c.storage))


def row(c, rid):
    return next(r for r in rows(c) if r["id"] == rid)


def ago(hours):
    from datetime import datetime, timezone

    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


class TestStaleJobs:
    def test_in_flight_over_2h_fails_and_refunds(self, client):
        old_q = seed(client, status="na_fila", ago=timedelta(hours=3))
        old_p = seed(client, status="processando", ago=timedelta(hours=2, minutes=1))
        fresh = seed(client, status="na_fila", ago=timedelta(minutes=90))
        sweep(client)
        for rid in (old_q, old_p):
            r = row(client, rid)
            assert r["status"] == "falhou" and r["erro_codigo"] == "tempo_esgotado"
            assert r["minutos_reembolsados"] is True and r["concluido_em"]
        assert row(client, fresh)["status"] == "na_fila"

    def test_expiry_refunds_the_minutes(self, client):
        # 29 min counted today, stuck for 3 h -> refunded (no longer counts toward the quota)
        rid = seed(client, status="na_fila", dur=1740.0, ago=timedelta(hours=3))
        sweep(client)
        assert row(client, rid)["minutos_reembolsados"] is True


class TestAudioRetention:
    def test_failed_audio_deleted_after_72h_not_before(self, client):
        old = seed(client, status="falhou")
        recent = seed(client, status="falhou")
        k_old, k_recent = put_audio(client, old), put_audio(client, recent)
        mark(client, old, concluido_em=ago(73))
        mark(client, recent, concluido_em=ago(71))
        sweep(client)
        assert not has_audio(client, k_old) and row(client, old)["audio_apagado_em"]
        assert has_audio(client, k_recent) and row(client, recent)["audio_apagado_em"] is None

    def test_failed_library_audio_follows_the_same_72h_rule(self, client):
        # third-party reel audio (origem='biblioteca') must never outlive the voice guarantees
        old = seed(client, status="falhou")
        recent = seed(client, status="falhou")
        for rid in (old, recent):
            mark(client, rid, origem="biblioteca", contexto_tipo="biblioteca_viral")
        k_old, k_recent = put_audio(client, old), put_audio(client, recent)
        mark(client, old, concluido_em=ago(73))
        mark(client, recent, concluido_em=ago(71))
        sweep(client)
        assert not has_audio(client, k_old) and row(client, old)["audio_apagado_em"]
        assert has_audio(client, k_recent)

    def test_library_leftovers_stale_jobs_and_transcripts_are_swept_too(self, client):
        done = seed(client, status="concluida")
        stuck = seed(client, status="processando", ago=timedelta(hours=3))
        for rid in (done, stuck):
            mark(client, rid, origem="biblioteca")
        key = put_audio(client, done)
        mark(client, done, concluido_em=ago(24 * 8), texto="t")
        sweep(client)
        assert not has_audio(client, key) and row(client, done)["texto"] is None
        assert row(client, stuck)["status"] == "falhou" and row(client, stuck)["minutos_reembolsados"] is True

    def test_leftover_audio_of_a_finished_job_is_retried(self, client):
        rid = seed(client, status="concluida")
        key = put_audio(client, rid)
        mark(client, rid, concluido_em=ago(2), texto="t")
        sweep(client)
        assert not has_audio(client, key) and row(client, rid)["audio_apagado_em"]

    def test_a_failing_delete_is_left_for_the_next_run(self, client):
        class Broken(type(client.storage)):
            async def delete(self, *, bucket, key):
                raise RuntimeError("down")

        rid = seed(client, status="falhou")
        mark(client, rid, concluido_em=ago(100))
        client.storage = Broken()
        sweep(client)
        assert row(client, rid)["audio_apagado_em"] is None  # not claimed deleted


class TestTranscriptPurge:
    def test_text_purged_after_7_days(self, client):
        old = seed(client, status="concluida")
        recent = seed(client, status="concluida")
        mark(client, old, concluido_em=ago(24 * 8), texto="velho", audio_apagado_em=ago(24 * 8))
        mark(client, recent, concluido_em=ago(24 * 6), texto="novo", audio_apagado_em=ago(24 * 6))
        sweep(client)
        assert row(client, old)["texto"] is None and row(client, recent)["texto"] == "novo"


class TestScheduling:
    def test_registered_every_15_minutes(self):
        assert scheduler.CRON == "7,22,37,52 * * * *"

    def test_never_raises(self, client):
        def boom():
            raise RuntimeError("db down")

        anyio.run(lambda: scheduler.run_sweep(db=boom, storage=lambda: client.storage))
