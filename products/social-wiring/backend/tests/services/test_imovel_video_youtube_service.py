"""`imovel_video_youtube_service` (migration 371): the ONE published YouTube video of an imóvel.

REPLACE semantics with the previous value kept in `imovel_historico`; an unknown código is the contract's 404; the Vista write-back of
`VideoDestaque` (+ our dated ObsVenda line with the motivo) happens only with the org switch on and never for a value that came FROM
Vista; a Vista failure is recorded in the history and never raised; URL/id parsing refuses a Short. MockSupabaseClient +
FakeVistaAdapter (the seed Fakes); nothing of ours is patched.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from noctusai_lib.domain.real_estate import Imovel
from noctusai_lib.integrations.vista import FakeVistaAdapter, VistaConfigError, VistaUpstreamError
from noctusai_lib.primitives.exceptions import AppException
from noctusai_lib.testing import MockSupabaseClient

from app.services import imovel_video_youtube_service as svc_mod
from app.services.imovel_video_youtube_service import VideoYoutubeInvalido, build_imovel_video_youtube_service, extrair_video_id

ORG = str(uuid4())
OUTRA = str(uuid4())
COD = "CA0001"
V1 = "dQw4w9WgXcQ"
V2 = "9bZkp7q19f0"
USER = "00000000-0000-4000-8000-0000000000a1"
JOB = "00000000-0000-4000-8000-00000000b0b0"


def _db(*, escrita: bool = False) -> MockSupabaseClient:
    db = MockSupabaseClient()
    db.set_table_data("imovel_registry", [{"org_id": ORG, "codigo_canonical": COD}, {"org_id": OUTRA, "codigo_canonical": "OU0001"}])
    db.set_table_data("imovel_video_youtube", [])
    db.set_table_data("imovel_historico", [])
    db.set_table_data("vista_divergencias_config", [{"org_id": ORG, "ativa": True, "vista_escrita_ativa": escrita}])
    return db


def _vista(**registro) -> FakeVistaAdapter:
    fake = FakeVistaAdapter(imoveis={COD: Imovel(codigo=COD)})
    fake.set_registro(COD, {"VideoDestaque": "", "ObsVenda": "Lote 3 quadra B\n10/10/26 Fulano informa visita. (CY)", **registro})
    return fake


def _svc(db, vista=None):
    return build_imovel_video_youtube_service(db, vista_provider=lambda _org: vista if vista is not None else _vista())


def _historico(db):
    return db.table("imovel_historico").select("*").execute().data


def _linhas(db):
    return db.table("imovel_video_youtube").select("*").execute().data


class TestDefinir:
    def test_sets_the_video_and_records_the_history(self):
        db = _db()
        v = _svc(db).definir(ORG, " ca0001 ", youtube_video_id=V1, origem="julia", motivo="Julia publicou o vídeo", upload_job_id=JOB)
        assert (v.codigo, v.youtube_video_id, v.youtube_url, v.origem, v.upload_job_id) == (
            COD, V1, f"https://www.youtube.com/watch?v={V1}", "julia", JOB)
        [row] = _linhas(db)
        assert row["org_id"] == ORG and row["codigo"] == COD and row["youtube_video_id"] == V1
        [h] = _historico(db)
        assert (h["acao"], h["origem"], h["campo"], h["valor_anterior"], h["valor_novo"], h["detalhe"]) == (
            "video_youtube_definido", "julia", "video_youtube", None, v.youtube_url, "Julia publicou o vídeo")

    def test_replace_newest_wins_and_the_old_value_stays_in_the_history(self):
        db = _db()
        svc = _svc(db)
        svc.definir(ORG, COD, youtube_video_id=V1, origem="julia", motivo="primeiro")
        v = svc.definir(ORG, COD, youtube_video_id=f"https://youtu.be/{V2}", origem="manual", motivo="trocado", definido_por=USER)
        [row] = _linhas(db)
        assert row["youtube_video_id"] == V2 and row["origem"] == "manual" and v.definido_por == USER
        assert svc.obter(ORG, COD).youtube_video_id == V2
        segundo = _historico(db)[-1]
        assert (segundo["valor_anterior"], segundo["valor_novo"], segundo["origem"], segundo["ator_user_id"]) == (
            svc_mod.url_de(V1), svc_mod.url_de(V2), "usuario", USER)

    def test_the_same_video_again_is_a_no_op(self):
        db = _db(escrita=True)
        vista = _vista()
        svc = _svc(db, vista)
        svc.definir(ORG, COD, youtube_video_id=V1, origem="julia", motivo="publicado")
        svc.definir(ORG, COD, youtube_video_id=V1, origem="julia", motivo="publicado (retry)")
        assert len(_linhas(db)) == 1 and [h["acao"] for h in _historico(db)] == ["video_youtube_definido", "enviado_ao_vista"]
        assert len(vista.atualizacoes) == 1

    def test_unknown_codigo_is_refused_with_the_contract_404(self):
        db = _db()
        with pytest.raises(AppException) as exc:
            _svc(db).definir(ORG, "OU0001", youtube_video_id=V1, origem="julia", motivo="x")  # another org's imóvel
        assert exc.value.status_code == 404
        assert _linhas(db) == [] and _historico(db) == []

    @pytest.mark.parametrize("kw", [{"motivo": "  "}, {"origem": "outra"}, {"youtube_video_id": "curto"}])
    def test_refuses_without_motivo_an_unknown_origem_or_a_bad_id(self, kw):
        db = _db(escrita=True)
        args = {"youtube_video_id": V1, "origem": "julia", "motivo": "ok", **kw}
        with pytest.raises(VideoYoutubeInvalido):
            _svc(db).definir(ORG, COD, **args)
        assert _linhas(db) == [] and _historico(db) == []


class TestVista:
    def test_switch_off_never_writes_vista(self):
        db = _db(escrita=False)
        vista = _vista()
        _svc(db, vista).definir(ORG, COD, youtube_video_id=V1, origem="julia", motivo="publicado")
        assert vista.atualizacoes == [] and [h["acao"] for h in _historico(db)] == ["video_youtube_definido"]

    def test_switch_on_sets_videodestaque_and_the_dated_obsvenda_line_with_the_motivo(self):
        db = _db(escrita=True)
        vista = _vista()
        _svc(db, vista).definir(ORG, COD, youtube_video_id=V1, origem="julia", motivo="Julia publicou o vídeo do imóvel")
        [(cod, campos)] = vista.atualizacoes
        url = svc_mod.url_de(V1)
        assert cod == COD and campos["VideoDestaque"] == url
        obs = campos["ObsVenda"].split("\n")
        assert obs[0] == "Lote 3 quadra B" and obs[2] == "10/10/26 Fulano informa visita. (CY)"  # header + old log untouched
        nota = obs[1]
        assert "Julia informa via YouTube" in nota and url in nota and "Julia publicou o vídeo do imóvel." in nota and nota.endswith("(NoctusAI)")
        enviado = _historico(db)[-1]
        assert (enviado["acao"], enviado["campo"], enviado["detalhe"]) == ("enviado_ao_vista", "video_youtube", nota)

    def test_a_value_from_vista_is_never_echoed_back(self):
        db = _db(escrita=True)
        vista = _vista(VideoDestaque=svc_mod.url_de(V1))
        v = _svc(db, vista).definir(ORG, COD, youtube_video_id=svc_mod.url_de(V1), origem="vista", motivo="importado do Vista")
        assert v.origem == "vista" and vista.atualizacoes == []
        [h] = _historico(db)
        assert (h["acao"], h["origem"]) == ("video_youtube_definido", "vista_sync")

    @pytest.mark.parametrize("falha", ["upstream", "sem_credencial"])
    def test_a_vista_failure_is_recorded_and_not_raised(self, falha):
        db = _db(escrita=True)
        vista = _vista()
        if falha == "upstream":
            vista.permitir_escrita(True, VistaUpstreamError(502, "bad gateway", "/imoveis/detalhes"))
            provider = lambda _org: vista  # noqa: E731
        else:
            def provider(_org):
                raise VistaConfigError("Vista não configurada")
        v = build_imovel_video_youtube_service(db, vista_provider=provider).definir(
            ORG, COD, youtube_video_id=V1, origem="julia", motivo="publicado")
        assert v.youtube_video_id == V1 and len(_linhas(db)) == 1  # our value is saved
        falhou = _historico(db)[-1]
        assert falhou["acao"] == "envio_vista_falhou" and falhou["valor_novo"] == svc_mod.url_de(V1)
        assert ("VistaUpstreamError" if falha == "upstream" else "VistaConfigError") in falhou["detalhe"]


class TestRemover:
    def test_removes_and_records_the_previous_value_without_touching_vista(self):
        db = _db(escrita=True)
        vista = _vista()
        svc = _svc(db, vista)
        svc.definir(ORG, COD, youtube_video_id=V1, origem="manual", motivo="definido")
        removido = svc.remover(ORG, COD, motivo="vídeo errado", definido_por=USER)
        assert removido.youtube_video_id == V1 and _linhas(db) == [] and svc.obter(ORG, COD) is None
        h = _historico(db)[-1]
        assert (h["acao"], h["valor_anterior"], h["valor_novo"], h["detalhe"], h["ator_user_id"]) == (
            "video_youtube_removido", svc_mod.url_de(V1), None, "vídeo errado", USER)
        assert len(vista.atualizacoes) == 1  # only the definir's write

    def test_nothing_to_remove_returns_none_and_writes_nothing(self):
        db = _db()
        assert _svc(db).remover(ORG, COD, motivo="x") is None and _historico(db) == []

    def test_remover_needs_a_motivo(self):
        with pytest.raises(VideoYoutubeInvalido):
            _svc(_db()).remover(ORG, COD, motivo="")


class TestExtrairVideoId:
    @pytest.mark.parametrize("valor", [
        V1, f"https://www.youtube.com/watch?v={V1}", f"youtube.com/watch?feature=share&v={V1}", f"https://m.youtube.com/watch?v={V1}&t=10s",
        f"https://youtu.be/{V1}?si=abc", f"https://www.youtube.com/embed/{V1}", f"https://www.youtube.com/live/{V1}", f"  {V1}  ",
    ])
    def test_accepts_the_id_and_the_usual_urls(self, valor):
        assert extrair_video_id(valor) == V1

    @pytest.mark.parametrize("valor", [
        "", "curto", f"https://www.youtube.com/shorts/{V1}", f"https://vimeo.com/{V1}", "https://www.youtube.com/watch?v=curto",
        "https://www.youtube.com/@canal", f"https://evil.example/watch?v={V1}",
    ])
    def test_refuses_shorts_other_hosts_and_garbage(self, valor):
        with pytest.raises(VideoYoutubeInvalido):
            extrair_video_id(valor)

    def test_a_short_says_why(self):
        with pytest.raises(VideoYoutubeInvalido, match="Shorts"):
            extrair_video_id(f"https://youtube.com/shorts/{V1}")
