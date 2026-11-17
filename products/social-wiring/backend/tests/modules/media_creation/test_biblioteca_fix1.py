"""FIX-1 (security review 2026-11-15 + the owner's legal decisions): F1 import-blob sweep, F2 transcripts through the
transcription organ, F3 opt-out re-check at job time, the 24-month review wrapper. Real seams + Fakes; nothing patched."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import anyio

from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.testing import MockSupabaseClient

from app.modules.media_creation import biblioteca_scheduler as sched
from app.modules.media_creation.services import biblioteca_service as svc

from .test_geracao_biblioteca_api import _PurgeRpc
from .test_geracao_biblioteca_ingestao import PID, _classificar, _db, _perfil, _ports, _transcrever, _viral, _vstatus, _rows

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
L = lambda n: f"00000000-0000-4000-8000-{n:012d}"  # noqa: E731 - a lote / perfil UUID


def _put(st, key, bucket=svc.BUCKET):
    anyio.run(lambda: st.put(bucket=bucket, key=key, data=b"x"))


def _keys(st, bucket=svc.BUCKET):
    return sorted(anyio.run(lambda: st.list_keys(bucket=bucket, prefix="", limit=1000)))


class TestImportacaoBlobSweep:
    """F1: ``importacoes/{lote}.json`` is the Estruturas load document; the sweep deletes the ones nobody needs."""

    def _lote(self, db, n, status, age):
        db.from_("cs_estrutura_importacoes").insert({"id": L(n), "status": status, "created_at": (NOW - age).isoformat()}).execute()
        _put(self.st, f"importacoes/{L(n)}.json")

    def test_each_state_follows_its_rule_and_a_foreign_key_is_counted_not_cast(self):
        db, self.st = MockSupabaseClient(), FakeStorageBackend()
        self._lote(db, 1, "concluida", timedelta(minutes=5))
        self._lote(db, 2, "falhou", timedelta(minutes=5))
        self._lote(db, 3, "simulada", timedelta(hours=2))      # inside its 24 h validity: kept
        self._lote(db, 4, "simulada", timedelta(hours=30))     # past it: gone
        self._lote(db, 5, "em_andamento", timedelta(days=1))   # running: kept
        self._lote(db, 6, "em_andamento", timedelta(days=8))   # stuck past the TTL: gone
        _put(self.st, f"importacoes/{L(7)}.json")              # no lote row at all (a dead letter that lost it): gone
        _put(self.st, "importacoes/lixo.json")                 # not {uuid}.json
        out = anyio.run(lambda: sched.varrer_blobs_importacao(db, self.st, now=NOW))
        assert out == {"apagados": 5, "falhos": 0, "segmentos_ignorados": 1}
        assert _keys(self.st) == sorted([f"importacoes/{L(3)}.json", f"importacoes/{L(5)}.json", "importacoes/lixo.json"])

    def test_a_failed_delete_is_counted_and_retried_the_next_night(self):
        db = MockSupabaseClient()

        class Flaky(FakeStorageBackend):
            fail = True

            async def delete(self, *, bucket, key):
                if self.fail:
                    raise RuntimeError("storage down")
                return await super().delete(bucket=bucket, key=key)

        self.st = st = Flaky()
        self._lote(db, 1, "concluida", timedelta(minutes=5))
        assert anyio.run(lambda: sched.varrer_blobs_importacao(db, st, now=NOW))["falhos"] == 1 and len(_keys(st)) == 1
        st.fail = False
        assert anyio.run(lambda: sched.varrer_blobs_importacao(db, st, now=NOW))["apagados"] == 1 and _keys(st) == []

    def test_the_nightly_retention_runs_it(self):
        db, st = MockSupabaseClient(), FakeStorageBackend()
        db.rpc = _PurgeRpc(db)
        _put(st, f"importacoes/{L(9)}.json")
        anyio.run(lambda: sched.run_retencao(client=lambda: db, storage=st, dias=90))
        assert _keys(st) == []


class TestTranscriptsThroughTheOrgan:
    """F2: a purge deletes the recording AND the text of every library transcription, in-flight jobs included."""

    def _seed(self, db, st, status, audio=True):
        db.from_("cs_perfis_monitorados").insert({"id": L(1), "org_id": None, "rede": "instagram", "handle": "alvo", "status": "ativo", "monitorar": True}).execute()
        db.from_("cs_virais").insert({"id": "v1", "org_id": None, "perfil_id": L(1), "ig_media_id": "m1"}).execute()
        db.from_("transcricoes").insert({
            "id": "t1", "contexto_tipo": "biblioteca_viral", "contexto_ref": "v1", "status": status,
            "storage_path": "org/user/t1.mp3", "texto": "fala de terceiro", "minutos_reembolsados": False,
        }).execute()
        if audio:
            _put(st, "org/user/t1.mp3", bucket="sw-transcricoes")

    def test_an_in_flight_job_is_closed_then_its_recording_and_row_are_erased(self):
        for status in ("processando", "na_fila", "concluida"):
            db, st = MockSupabaseClient(), FakeStorageBackend()
            db.rpc = _PurgeRpc(db)
            self._seed(db, st, status)
            perfil = db.from_("cs_perfis_monitorados").select("*").execute().data[0]
            anyio.run(lambda: svc.purgar_perfil(db, st, perfil, tipo_evento="optout_purgado", apagar_estruturas=True))
            assert db.from_("transcricoes").select("*").execute().data == [], status
            assert _keys(st, "sw-transcricoes") == [], status

    def test_a_recording_that_cannot_be_deleted_keeps_its_row_without_the_text_for_the_organs_sweep(self):
        class Flaky(FakeStorageBackend):
            async def delete(self, *, bucket, key):
                if bucket == "sw-transcricoes":
                    raise RuntimeError("storage down")
                return await super().delete(bucket=bucket, key=key)

        db, st = MockSupabaseClient(), Flaky()
        db.rpc = _PurgeRpc(db)
        self._seed(db, st, "concluida")
        perfil = db.from_("cs_perfis_monitorados").select("*").execute().data[0]
        out = anyio.run(lambda: svc.purgar_perfil(db, st, perfil, tipo_evento="optout_purgado", apagar_estruturas=True))
        (row,) = db.from_("transcricoes").select("*").execute().data
        assert row["texto"] is None and row["id"] == "t1" and out["blobs_falhos"] == 1  # the organ's retention sweep retries the audio


class TestOptOutRecheckAtJobTime:
    """F3: a creator who opted out after the video was queued costs no transcription and no model call."""

    def _optout(self, db):
        db.from_("cs_biblioteca_optouts").insert({"id": "o1", "handle": "alvo", "origem": "dpo"}).execute()
        db.rpc = _PurgeRpc(db)

    def test_classify_erases_the_profile_and_never_calls_the_model(self):
        db = _db()
        _viral(db, status="concluida")
        self._optout(db)
        _classificar(_ports(db))  # the default LLM raises if it is called
        assert _rows(db) == [] and db.from_("cs_perfis_monitorados").select("*").execute().data == []
        assert [(e["tipo"], e["ator_tipo"]) for e in db.from_("cs_perfil_eventos").select("*").execute().data] == [("optout_purgado", "sistema")]

    def test_transcribe_erases_the_profile_and_downloads_nothing(self):
        db = _db()
        _viral(db, status="pendente")
        self._optout(db)
        from .test_geracao_biblioteca_ingestao import FakeTranscricao

        tr = FakeTranscricao()
        _transcrever(_ports(db, transcricao=tr))
        assert tr.calls == [] and _rows(db) == []

    def test_a_creator_who_did_not_opt_out_is_processed_as_before(self):
        db = _db()
        _viral(db, status="pendente")
        db.rpc = _PurgeRpc(db)
        _transcrever(_ports(db))  # no fetcher entry: the plain path proceeds to a (failing) download, not a purge
        assert _perfil(db)["id"] == PID and _vstatus(db)["id"] == "v1"


class TestRevisaoPorDesuso:
    def test_the_wrapper_calls_the_rpc_with_24_months_and_returns_its_counts(self):
        db = MockSupabaseClient()
        db.rpc = rpc = _PurgeRpc(db)
        rpc.revisao_resposta = {"sinalizadas": 3, "liberadas": 1}
        assert sched.sinalizar_revisao_por_desuso(db) == {"sinalizadas": 3, "liberadas": 1}
        assert rpc.revisao_calls == [{"p_meses": 24}] and sched.REVISAO_DESUSO_MESES == 24
