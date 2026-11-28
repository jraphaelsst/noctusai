"""`imovel_videos_vista_import_service` (S3): fill `imovel_video_youtube` from Vista's `Video` relation.

Selection: Destaque wins, else the first YouTube one by VideoCodigo; a Short / a non-YouTube video is skipped and counted. Rule 3:
a julia/manual row is never overwritten; a vista row is updated only when Vista's id differs; the same id is `ja_igual`. Vista
outcomes: an unpublished stub, an unknown code, a failure, an abort after N failures in a row. `dry_run` writes NOTHING. A re-run
is idempotent. MockSupabaseClient + FakeVistaAdapter (the seed Fakes); nothing of ours is patched.
"""
from __future__ import annotations

import asyncio
import contextlib
from uuid import uuid4

from noctusai_lib.integrations.vista import FakeVistaAdapter, VistaNotFound, VistaRecordUnpublished, VistaUpstreamError
from noctusai_lib.testing import MockSupabaseClient

from app.services import imovel_videos_vista_import_service as imp

ORG = str(uuid4())
OUTRA = str(uuid4())
V1, V2, V3 = "dQw4w9WgXcQ", "9bZkp7q19f0", "9cgV72Lq9gs"


def _v(codigo: str, video: str, *, tipo: str = "youtube", destaque: str = "Nao") -> dict:
    return {"Codigo": "X", "VideoCodigo": codigo, "Video": video, "Tipo": tipo, "Destaque": destaque, "ExibirNoSite": "Sim"}


def _db(codigos=("CA0001",), videos=()) -> MockSupabaseClient:
    db = MockSupabaseClient()
    db.set_table_data("imovel_registry", [{"org_id": ORG, "codigo_canonical": c, "codigo_display": c} for c in codigos]
                      + [{"org_id": OUTRA, "codigo_canonical": "OU0001", "codigo_display": "OU0001"}])
    db.set_table_data("imovel_video_youtube", [{"org_id": ORG, **v} for v in videos])
    db.set_table_data("imovel_historico", [])
    db.set_table_data("vista_divergencias_config", [{"org_id": ORG, "ativa": True, "vista_escrita_ativa": True}])
    return db


def _rodar(db, vista, *, pagina: int = imp.PAGINA, **kw) -> imp.Relatorio:
    return asyncio.run(imp.ImovelVideosVistaImportService(db, vista, pagina=pagina).importar(ORG, **kw))


def _linhas(db):
    return db.table("imovel_video_youtube").select("*").execute().data


def _historico(db):
    return db.table("imovel_historico").select("*").execute().data


def _linha(rel, codigo):
    return next(x for x in rel.linhas if x.codigo == codigo)


class TestEscolha:
    def test_destaque_wins(self):
        vista = FakeVistaAdapter()
        vista.add_imovel_videos("CA0001", {"1": _v("1", V1), "2": _v("2", V2, destaque="Sim")})
        linha = _linha(_rodar(_db(), vista), "CA0001")
        assert (linha.resultado, linha.youtube_video_id) == ("criaria", V2)

    def test_without_destaque_the_lowest_video_codigo_wins(self):
        vista = FakeVistaAdapter()
        vista.add_imovel_videos("CA0001", {"10": _v("10", V2), "9": _v("9", V1)})
        linha = _linha(_rodar(_db(), vista), "CA0001")
        assert (linha.youtube_video_id, linha.video_codigo, linha.youtube_url) == (V1, "9", f"https://www.youtube.com/watch?v={V1}")

    def test_a_full_url_is_parsed_and_a_youtube_url_counts_whatever_the_tipo(self):
        vista = FakeVistaAdapter()
        vista.add_imovel_videos("CA0001", [_v("1", f"https://youtu.be/{V3}", tipo="")])
        assert _linha(_rodar(_db(), vista), "CA0001").youtube_video_id == V3

    def test_a_short_is_skipped_and_the_next_youtube_one_is_taken(self):
        vista = FakeVistaAdapter()
        vista.add_imovel_videos("CA0001", [_v("1", f"https://www.youtube.com/shorts/{V1}", destaque="Sim"), _v("2", V2)])
        assert _linha(_rodar(_db(), vista), "CA0001").youtube_video_id == V2

    def test_only_shorts_is_short_ignorado_and_nothing_is_written(self):
        vista = FakeVistaAdapter()
        vista.add_imovel_videos("CA0001", [_v("1", f"https://youtube.com/shorts/{V1}"), _v("2", V2, tipo="youtube_shorts")])
        db = _db()
        rel = _rodar(db, vista, dry_run=False)
        assert rel.contagens["short_ignorado"] == 1 and _linhas(db) == []

    def test_a_non_youtube_video_is_nao_youtube_even_with_an_11_char_value(self):
        vista = FakeVistaAdapter()
        vista.add_imovel_videos("CA0001", [_v("1", "abcdefghijk", tipo="vimeo"), _v("2", "https://vimeo.com/123", tipo="vimeo")])
        rel = _rodar(_db(), vista)
        assert rel.contagens["nao_youtube"] == 1 and rel.contagens["criaria"] == 0

    def test_no_video_is_sem_video(self):
        rel = _rodar(_db(), FakeVistaAdapter())
        assert rel.contagens["sem_video"] == 1 and rel.contagens["consultados"] == 1


class TestRegra3:
    def _vista(self, vid=V1):
        vista = FakeVistaAdapter()
        vista.add_imovel_videos("CA0001", [_v("1", vid)])
        return vista

    def test_a_missing_row_is_created_with_origem_vista_and_history(self):
        db = _db()
        rel = _rodar(db, self._vista(), dry_run=False, definido_por="00000000-0000-4000-8000-0000000000a1")
        assert rel.status == "concluida" and rel.contagens["criados"] == 1
        [row] = _linhas(db)
        assert (row["codigo"], row["youtube_video_id"], row["origem"]) == ("CA0001", V1, "vista")
        [h] = _historico(db)
        assert h["origem"] == "vista_sync" and h["acao"] == "video_youtube_definido" and "VideoCodigo 1" in h["detalhe"]

    def test_a_real_run_never_writes_to_vista_even_with_the_org_switch_on(self):
        vista = self._vista()
        _rodar(_db(), vista, dry_run=False)
        assert vista.atualizacoes == []

    def test_julia_and_manual_rows_are_kept(self):
        for origem in ("julia", "manual"):
            db = _db(videos=[{"codigo": "CA0001", "youtube_video_id": V2, "origem": origem}])
            rel = _rodar(db, self._vista(), dry_run=False)
            assert rel.contagens["mantido_julia_manual"] == 1, origem
            assert [(r["youtube_video_id"], r["origem"]) for r in _linhas(db)] == [(V2, origem)]
            linha = _linha(rel, "CA0001")
            assert (linha.atual_youtube_video_id, linha.atual_origem, linha.youtube_video_id) == (V2, origem, V1)

    def test_a_vista_row_is_updated_when_different(self):
        db = _db(videos=[{"codigo": "CA0001", "youtube_video_id": V2, "origem": "vista"}])
        rel = _rodar(db, self._vista(), dry_run=False)
        assert rel.contagens["atualizados"] == 1 and [r["youtube_video_id"] for r in _linhas(db)] == [V1]

    def test_the_same_id_is_ja_igual_and_writes_nothing(self):
        db = _db(videos=[{"codigo": "CA0001", "youtube_video_id": V1, "origem": "vista"}])
        rel = _rodar(db, self._vista(), dry_run=False)
        assert rel.contagens["ja_igual"] == 1 and _historico(db) == []

    def test_a_rerun_is_idempotent(self):
        db = _db()
        _rodar(db, self._vista(), dry_run=False)
        rel = _rodar(db, self._vista(), dry_run=False)
        assert rel.contagens["ja_igual"] == 1 and rel.contagens["criados"] == 0 and len(_linhas(db)) == 1 and len(_historico(db)) == 1


class TestDryRun:
    def test_dry_run_is_the_default_and_writes_nothing(self):
        vista = FakeVistaAdapter()
        vista.add_imovel_videos("CA0001", [_v("1", V1)])
        vista.add_imovel_videos("CA0002", [_v("1", V2)])
        db = _db(codigos=("CA0001", "CA0002"), videos=[{"codigo": "CA0002", "youtube_video_id": V1, "origem": "vista"}])
        antes = (_linhas(db), _historico(db))
        rel = _rodar(db, vista)
        assert rel.dry_run is True and (rel.contagens["criaria"], rel.contagens["atualizaria"]) == (1, 1)
        assert (rel.contagens["criados"], rel.contagens["atualizados"]) == (0, 0)
        assert (_linhas(db), _historico(db)) == antes and vista.atualizacoes == []


class TestVista:
    def test_unpublished_and_unknown_codes_are_counted_apart(self):
        vista = FakeVistaAdapter()
        vista.falhar_videos("CA0001", VistaRecordUnpublished("CA0001", "/imoveis/detalhes", ["Corretor"]))
        vista.falhar_videos("CA0002", VistaRecordUnpublished("CA0002", "/imoveis/detalhes", []))
        vista.falhar_videos("CA0003", VistaNotFound(404, "x", "/imoveis/detalhes"))
        rel = _rodar(_db(codigos=("CA0001", "CA0002", "CA0003")), vista)
        assert (rel.contagens["nao_publicado"], rel.contagens["nao_encontrado"], rel.contagens["erros"]) == (1, 2, 0)
        assert rel.status == "concluida"

    def test_a_failure_is_an_error_row_with_the_class_name_only(self):
        vista = FakeVistaAdapter()
        vista.falhar_videos("CA0001", VistaUpstreamError(500, "body com a chave secreta", "/imoveis/detalhes"))
        vista.add_imovel_videos("CA0002", [_v("1", V1)])
        rel = _rodar(_db(codigos=("CA0001", "CA0002")), vista)
        assert rel.contagens["erros"] == 1 and rel.contagens["criaria"] == 1
        assert _linha(rel, "CA0001").motivo == "leitura do Vista falhou (VistaUpstreamError)"

    def test_too_many_failures_in_a_row_abort_the_run(self):
        codigos = [f"CA{i:04d}" for i in range(imp.MAX_ERROS_SEGUIDOS + 5)]
        vista = FakeVistaAdapter()
        for c in codigos:
            vista.falhar_videos(c, VistaUpstreamError(401, "x", "/imoveis/detalhes"))
        rel = _rodar(_db(codigos=codigos), vista)
        assert rel.status == "abortada" and rel.contagens["consultados"] == imp.MAX_ERROS_SEGUIDOS


class TestEscopo:
    def test_codigos_filter_canonicalises_and_reports_codes_outside_the_registry(self):
        vista = FakeVistaAdapter()
        vista.add_imovel_videos("CA0002", [_v("1", V1)])
        rel = _rodar(_db(codigos=("CA0001", "CA0002")), vista, codigos=[" ca0002 ", "ZZ9999", "OU0001"])
        assert rel.contagens["consultados"] == 1 and rel.contagens["nao_cadastrado"] == 2  # another org's code is not ours
        assert _linha(rel, "CA0002").resultado == "criaria"

    def test_limite_cuts_the_run(self):
        rel = _rodar(_db(codigos=("CA0001", "CA0002", "CA0003")), FakeVistaAdapter(), limite=2)
        assert rel.contagens["consultados"] == 2 and rel.total_codigos == 2

    def test_the_registry_and_the_field_are_read_in_pages(self):
        codigos = [f"CA{i:04d}" for i in range(5)]
        vista = FakeVistaAdapter()
        for c in codigos:
            vista.add_imovel_videos(c, [_v("1", V1)])
        db = _db(codigos=codigos, videos=[{"codigo": c, "youtube_video_id": V1, "origem": "vista"} for c in codigos])
        rel = _rodar(db, vista, pagina=2)
        assert rel.contagens["consultados"] == 5 and rel.contagens["ja_igual"] == 5


class TestExecucoes:
    def test_single_flight_per_org_and_the_lease_refusal_is_reported(self):
        regs = imp.Execucoes()
        a, nova = regs.iniciar(ORG, dry_run=True, codigos=None, limite=None, iniciado_por=None)
        b, nova_b = regs.iniciar(ORG, dry_run=False, codigos=None, limite=None, iniciado_por=None)
        assert nova and not nova_b and a.id == b.id

        @contextlib.contextmanager
        def negado(*_a, **_k):
            yield False

        rel = asyncio.run(imp.executar(a, client=_db(), admin=None, adapter=FakeVistaAdapter(), lease_fn=negado))
        assert rel.status == "ignorada" and regs.em_andamento(ORG) is None

    def test_report_rows_filter_and_page(self):
        vista = FakeVistaAdapter()
        vista.add_imovel_videos("CA0002", [_v("1", V1)])
        rel = _rodar(_db(codigos=("CA0001", "CA0002", "CA0003")), vista)
        d = rel.as_dict(resultados=imp.RESULTADOS_ACIONAVEIS)
        assert d["linhas_total"] == 1 and d["linhas"][0]["codigo"] == "CA0002" and d["contagens"]["sem_video"] == 2
        assert rel.as_dict(limit=1, offset=1)["linhas"][0]["codigo"] == "CA0002"
