"""POST/GET/DELETE /api/transcricoes — validation order, quotas, errors, auth
(transcription-contract.md sections 3 and 4)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from noctusai_lib.integrations.transcription import (
    FakeTranscriber,
    TranscriberBusy,
    TranscriberUnavailable,
    TranscriptionRejected,
)

from app.modules.transcricoes import hooks
from app.modules.transcricoes.deps import BUCKET
from tests.modules.transcricoes.conftest import AUDIO, ORG, USER, probe

URL = "/api/transcricoes"
CTX = "teste_ctx"


@pytest.fixture(autouse=True)
def _ctx():
    """A recording context, so these tests stand alone from any consumer module."""
    hooks.register_contexto(
        CTX,
        validar=lambda db, org, user, ref: _validar(ref),
        aplicar=lambda db, row: None,
    )
    yield


def _validar(ref: str) -> None:
    from app.modules.transcricoes.errors import TranscricaoErro

    if ref == "alheio":
        raise TranscricaoErro("nao_encontrada")


class CountingTranscriber(FakeTranscriber):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.probe_calls = 0

    async def probe(self, audio):
        self.probe_calls += 1
        return await super().probe(audio)


class RaisingProbe(FakeTranscriber):
    def __init__(self, exc):
        super().__init__()
        self._exc = exc

    async def probe(self, audio):
        raise self._exc


def post(c, data=AUDIO, ctx=CTX, ref="ref-1", name="voz.webm"):
    return c.post(
        URL, files={"arquivo": (name, data, "audio/webm")}, data={"contexto_tipo": ctx, "contexto_ref": ref}
    )


def _get_blob(c, key):
    import anyio

    return anyio.run(lambda: c.storage.get(bucket=BUCKET, key=key))


def rows(c):
    return c.mock_supabase.from_("transcricoes").select("*").execute().data


def seed(c, *, user=USER, org=ORG, status="concluida", dur=60.0, ago=timedelta(minutes=1), refunded=False):
    rid = str(uuid.uuid4())
    c.mock_supabase.from_("transcricoes").insert({
        "id": rid, "org_id": org, "user_id": user, "contexto_tipo": CTX, "contexto_ref": "r",
        "storage_path": f"{org}/{user}/{rid}.webm", "bytes": 10, "duracao_s": dur, "formato": "webm",
        "status": status, "criado_em": (datetime.now(timezone.utc) - ago).isoformat(),
        "minutos_reembolsados": refunded, "audio_apagado_em": None,
    }).execute()
    return rid


class TestSubmitOk:
    def test_202_row_audio_and_job(self, client):
        client.transcriber = FakeTranscriber(default_probe=probe(42.0))
        r = post(client)
        assert r.status_code == 202, r.text
        d = r.json()["data"]
        assert d["status"] == "na_fila" and d["posicao"] == 1 and d["duracao_s"] == 42.0
        assert d["estimativa_s"] > 0
        [row] = rows(client)
        assert row["id"] == d["id"] and row["org_id"] == ORG and row["user_id"] == USER
        assert row["status"] == "na_fila" and row["formato"] == "webm" and row["bytes"] == len(AUDIO)
        # quota is charged on the PROBED duration
        assert row["duracao_s"] == 42.0
        # private path org/user/uuid.ext, never the client's filename
        assert row["storage_path"] == f"{ORG}/{USER}/{row['id']}.webm"
        assert "voz" not in row["storage_path"]
        assert "storage_path" not in d
        assert _get_blob(client, row["storage_path"]).data == AUDIO
        job = list(client.jobs._jobs.values())[0]
        assert job.type == "transcricao" and job.payload == {"transcricao_id": row["id"]}

    def test_position_counts_those_ahead(self, client):
        seed(client, status="processando", dur=120.0, user="other", ago=timedelta(minutes=5))
        d = post(client).json()["data"]
        assert d["posicao"] == 2


class TestValidationOrder:
    def test_kill_switch_off_is_503_and_nothing_is_stored(self, client):
        client.habilitada = False
        r = post(client)
        assert r.status_code == 503 and r.json()["codigo"] == "transcricao_desativada"
        assert r.headers["Retry-After"]
        assert rows(client) == [] and client.jobs._jobs == {}

    def test_413_stream_cut_over_15mb(self, client):
        client.transcriber = CountingTranscriber()
        big = b"\x1a\x45\xdf\xa3" + b"\x00" * (15 * 1024 * 1024)  # 15 MB + 4 bytes
        r = post(client, data=big)
        assert r.status_code == 413 and r.json()["codigo"] == "arquivo_grande"
        assert "15 MB" in r.json()["mensagem"] and r.json()["detail"] == r.json()["mensagem"]
        assert client.transcriber.probe_calls == 0 and rows(client) == []

    def test_size_is_checked_before_magic_bytes(self, client):
        r = post(client, data=b"not-audio" + b"\x00" * (15 * 1024 * 1024))
        assert r.status_code == 413

    def test_415_unknown_magic_bytes_never_probed(self, client):
        client.transcriber = CountingTranscriber()
        r = post(client, data=b"MZ\x90\x00" + b"\x00" * 100, name="x.webm")
        assert r.status_code == 415 and r.json()["codigo"] == "formato_invalido"
        assert client.transcriber.probe_calls == 0 and rows(client) == []

    def test_unknown_context_is_422(self, client):
        r = post(client, ctx="nao_existe")
        assert r.status_code == 422 and r.json()["codigo"] == "contexto_invalido"
        assert rows(client) == []

    def test_foreign_context_ref_is_404(self, client):
        r = post(client, ref="alheio")
        assert r.status_code == 404 and rows(client) == []

    @pytest.mark.parametrize("dur,codigo", [(0.4, "audio_vazio"), (601.0, "duracao_excedida")])
    def test_422_probed_duration(self, client, dur, codigo):
        client.transcriber = FakeTranscriber(default_probe=probe(dur))
        r = post(client)
        assert r.status_code == 422 and r.json()["codigo"] == codigo
        assert rows(client) == []

    def test_422_probed_codec_not_allowed(self, client):
        client.transcriber = FakeTranscriber(default_probe=probe(5.0, "webm", "vp9"))
        r = post(client)
        assert r.status_code == 422 and r.json()["codigo"] == "formato_invalido"

    def test_422_probe_rejects_corrupt_audio(self, client):
        client.transcriber = RaisingProbe(TranscriptionRejected("audio_corrompido"))
        r = post(client)
        assert r.status_code == 422 and r.json()["codigo"] == "audio_corrompido"
        assert rows(client) == []

    def test_probe_unavailable_is_503_not_charged(self, client):
        client.transcriber = RaisingProbe(TranscriberUnavailable("down"))
        r = post(client)
        assert r.status_code == 503 and r.json()["codigo"] == "transcricao_indisponivel"
        assert r.headers["Retry-After"] and rows(client) == []

    def test_probe_busy_is_503_with_the_engine_hint(self, client):
        client.transcriber = RaisingProbe(TranscriberBusy(23))
        r = post(client)
        assert r.status_code == 503 and r.headers["Retry-After"] == "23"

    def test_unconfigured_transcriber_is_503(self, client):
        from noctusai_lib.integrations.transcription import TranscriptionNotConfigured

        client.transcriber = RaisingProbe(TranscriptionNotConfigured("no url"))
        r = post(client)
        assert r.status_code == 503 and r.json()["codigo"] == "transcricao_indisponivel"

    def test_storage_failure_releases_the_reservation(self, client):
        class Broken(type(client.storage)):
            async def put(self, **kw):
                raise RuntimeError("storage down")

        client.storage = Broken()
        r = post(client)
        assert r.status_code == 503
        [row] = rows(client)
        assert row["status"] == "falhou" and row["minutos_reembolsados"] is True
        assert client.jobs._jobs == {}


class TestQuotas:
    def test_two_in_flight_then_429(self, client):
        assert post(client).status_code == 202
        assert post(client).status_code == 202
        r = post(client)
        assert r.status_code == 429 and r.json()["codigo"] == "limite_usuario"
        assert int(r.headers["Retry-After"]) >= 1

    def test_ten_per_hour(self, client):
        for _ in range(10):
            seed(client, dur=5.0, ago=timedelta(minutes=30))
        r = post(client)
        assert r.status_code == 429 and r.json()["codigo"] == "limite_usuario"
        assert int(r.headers["Retry-After"]) >= 60

    def test_user_30_minutes_rolling_24h(self, client):
        seed(client, dur=1790.0, ago=timedelta(hours=3))
        client.transcriber = FakeTranscriber(default_probe=probe(11.0))
        r = post(client)
        assert r.status_code == 429 and r.json()["codigo"] == "cota_diaria_usuario"
        assert int(r.headers["Retry-After"]) > 3600

    def test_user_window_rolls_off_after_24h(self, client):
        seed(client, dur=1790.0, ago=timedelta(hours=25))
        client.transcriber = FakeTranscriber(default_probe=probe(11.0))
        assert post(client).status_code == 202

    def test_refunded_minutes_do_not_count(self, client):
        seed(client, dur=1790.0, status="falhou", refunded=True, ago=timedelta(hours=1))
        client.transcriber = FakeTranscriber(default_probe=probe(60.0))
        assert post(client).status_code == 202

    def test_org_120_minutes_per_day(self, client):
        for i in range(4):  # 4 other users x 25 min = 100 min
            seed(client, user=f"u{i}", dur=1500.0, ago=timedelta(hours=2))
        client.transcriber = FakeTranscriber(default_probe=probe(600.0))
        assert post(client).status_code == 202  # 100 + 10 = 110 min <= 120
        seed(client, user="u9", dur=1000.0, ago=timedelta(hours=2))  # 110 + 16.7 = 126.7 min
        client.transcriber = FakeTranscriber(default_probe=probe(30.0))
        r = post(client)
        assert r.status_code == 429 and r.json()["codigo"] == "cota_diaria_org"

    def test_queue_depth_20_is_503(self, client):
        for i in range(20):
            seed(client, user=f"o{i}", org=f"org-{i}", status="na_fila", dur=5.0)
        r = post(client)
        assert r.status_code == 503 and r.json()["codigo"] == "fila_cheia"
        assert r.headers["Retry-After"]

    def test_global_daily_capacity_is_503(self, client):
        for i in range(20):
            seed(client, user=f"g{i}", org=f"org-{i}", dur=1790.0, ago=timedelta(hours=1))  # 596 min
        client.transcriber = FakeTranscriber(default_probe=probe(300.0))
        r = post(client)
        assert r.status_code == 503 and r.json()["codigo"] == "capacidade_diaria"


class TestReadAndCancel:
    def test_get_own_job(self, client):
        d = post(client).json()["data"]
        g = client.get(f"{URL}/{d['id']}")
        assert g.status_code == 200
        body = g.json()["data"]
        assert body["status"] == "na_fila" and body["posicao"] == 1 and body["texto"] is None
        assert body["erro"] is None and "storage_path" not in body

    def test_get_finished_and_failed_shapes(self, client):
        rid = seed(client, status="concluida")
        client.mock_supabase.from_("transcricoes").update({"texto": "olá"}).eq("id", rid).execute()
        assert client.get(f"{URL}/{rid}").json()["data"]["texto"] == "olá"
        bad = seed(client, status="falhou")
        client.mock_supabase.from_("transcricoes").update({"erro_codigo": "audio_corrompido"}).eq("id", bad).execute()
        erro = client.get(f"{URL}/{bad}").json()["data"]["erro"]
        assert erro["codigo"] == "audio_corrompido" and erro["mensagem"]

    def test_other_users_job_is_404_never_403(self, client):
        rid = seed(client, user="someone-else")
        for r in (client.get(f"{URL}/{rid}"), client.delete(f"{URL}/{rid}")):
            assert r.status_code == 404 and r.json()["codigo"] == "nao_encontrada"

    def test_other_orgs_job_is_404(self, client):
        rid = seed(client, org="another-org")
        assert client.get(f"{URL}/{rid}").status_code == 404

    def test_unknown_id_is_404(self, client):
        assert client.get(f"{URL}/{uuid.uuid4()}").status_code == 404

    def test_cancel_queued_refunds_and_deletes_audio(self, client):
        d = post(client).json()["data"]
        r = client.delete(f"{URL}/{d['id']}")
        assert r.status_code == 200 and r.json()["data"]["status"] == "cancelada"
        [row] = rows(client)
        assert row["status"] == "cancelada" and row["minutos_reembolsados"] is True
        assert row["audio_apagado_em"]
        assert _get_blob(client, row["storage_path"]) is None

    def test_cancel_processing_is_409(self, client):
        rid = seed(client, status="processando")
        r = client.delete(f"{URL}/{rid}")
        assert r.status_code == 409 and r.json()["codigo"] == "em_processamento"

    def test_cancel_finished_is_409(self, client):
        rid = seed(client, status="concluida")
        assert client.delete(f"{URL}/{rid}").status_code == 409

    def test_cancelled_minutes_free_the_quota(self, client):
        client.transcriber = FakeTranscriber(default_probe=probe(600.0))
        ids = [post(client).json()["data"]["id"] for _ in range(2)]
        assert post(client).status_code == 429
        assert client.delete(f"{URL}/{ids[0]}").status_code == 200
        assert post(client).status_code == 202


class TestStats:
    def test_admin_only(self, client):
        assert client.get(f"{URL}/_stats").status_code == 403

    def test_admin_gets_queue_and_daily_minutes_per_org(self, client):
        client.admin_ids.add(USER)
        seed(client, dur=120.0)
        seed(client, org="org-b", user="b", dur=60.0)
        seed(client, dur=300.0, status="falhou", refunded=True)
        r = client.get(f"{URL}/_stats")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["ultimas_24h"]["minutos_por_org"] == {ORG: 2.0, "org-b": 1.0}
        assert d["ultimas_24h"]["minutos_total"] == 3.0
        assert d["ultimas_24h"]["por_status"]["concluida"] == 2
        assert "pending" in d["queue_stats"]


class TestAuthBoundary:
    @pytest.mark.parametrize("method,path,kw", [
        ("post", "", {"files": {"arquivo": ("a.webm", AUDIO, "audio/webm")},
                      "data": {"contexto_tipo": CTX, "contexto_ref": "r"}}),
        ("get", f"/{uuid.uuid4()}", {}),
        ("delete", f"/{uuid.uuid4()}", {}),
        ("get", "/_stats", {}),
    ])
    def test_unauthenticated_is_401(self, client, method, path, kw):
        r = getattr(client.raw(), method)(URL + path, **kw)
        assert r.status_code == 401, (path, r.status_code, r.text)
