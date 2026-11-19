"""CoreStudio criação pipeline, slice S5 (criacao-pipeline-contract 1, 3): stage model from DATA, the Criação gate
(``headline_nao_aprovado``), routes, the ``system`` mover and the live stream.

Real seams: the module ``client`` fixture's mock Supabase; stages seeded by the seed ``ensure_default_stages``; the
approvals organ's rows (``apr_events``) seeded like the roteiro tests do. The ONE emulated seam is the Postgres RPC
``cs_post_criacao_transicionar`` (migration 369), whose real behaviour is pinned by ``test_migration_cs_criacao_estado``
on PGlite -- here it only reproduces its optimistic ``p_de`` check + the state/event writes.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from noctusai_lib.domain.approvals import ApprovalStore, FakeApprovalLedger, table_specs
from noctusai_lib.domain.pipeline import pipeline_scope
from noctusai_lib.domain._organ_common import make_org_table_store

from app.modules.media_creation import criacao_estado as est
from app.modules.media_creation import esteira_config as cfg
from app.modules.media_creation.criacao_rotas import ROTAS, resolver_rota
from app.modules.media_creation.routers.esteira import get_headline_approvals
from app.modules.media_creation.services import roteiro_aprovacao as apr
from app.modules.media_creation.services.criacao_mover import SISTEMA_ATOR_ID, CriacaoError, CriacaoMover
from app.modules.media_creation.services.esteira_service import EsteiraService

from .test_esteira_api import BASE, MARCA, ORG, _aprovar, _aprovar_headline, _headline, _id, _ins, _mover, _post, _roteiro, _stages, ec  # noqa: F401


# ── seams ───────────────────────────────────────────────────────────────────


class RecBus:
    """A recording bus: the publish half of the realtime bus, nothing else."""

    def __init__(self):
        self.frames: list[tuple[str, str, dict]] = []

    async def publish(self, scope, event, payload):
        self.frames.append((scope, event, payload))
        return "1-0"


class TransicaoRpc:
    """Emulates ``cs_post_criacao_transicionar`` (369) over the mock tables: optimistic ``p_de``, state + event."""

    def __init__(self, db):
        self.db = db
        self.calls: list[dict] = []

    def __call__(self, name, params):
        assert name == "cs_post_criacao_transicionar", name
        self.calls.append(params)
        return SimpleNamespace(execute=lambda: self._run(params))

    def _run(self, p):
        rows = self.db.from_("cs_posts").select("*").eq("id", p["p_post"]).eq("org_id", p["p_org"]).execute().data
        if not rows:
            raise Exception("post_nao_encontrado")
        if rows[0].get("criacao_estado") != p["p_de"]:
            raise Exception(f"estado_mudou: esperado {p['p_de']}, atual {rows[0].get('criacao_estado')}")
        upd = {"criacao_estado": p["p_para"], "falha_codigo": p["p_falha_codigo"] if p["p_para"] == "falhou" else None}
        if p["p_rota"]:
            upd["criacao_rota"] = p["p_rota"]
        self.db.from_("cs_posts").update(upd).eq("id", p["p_post"]).execute()
        if p["p_tipo"]:
            self.db.from_("cs_post_eventos").insert(
                {"org_id": p["p_org"], "post_id": p["p_post"], "tipo": p["p_tipo"], "de": p["p_de"], "para": p["p_para"],
                 "dados": p["p_dados"], "ator_id": p["p_ator"]}
            ).execute()
        return SimpleNamespace(data={"post_id": p["p_post"]})


@pytest.fixture
def mv(ec):
    sb = ec.mock_supabase
    sb.rpc = TransicaoRpc(sb)
    # the approvals organ's own Fake ledger (the Fake the organ ships): the write seam of the headline approval endpoints
    tables = make_org_table_store(table_specs(apr.CFG), supabase_client=sb)
    store = ApprovalStore(tables, FakeApprovalLedger(tables))
    ec._tc.app.dependency_overrides[get_headline_approvals] = lambda: apr.make_approvals(sb, store=store)
    bus = RecBus()
    return SimpleNamespace(ec=ec, sb=sb, bus=bus, mover=CriacaoMover(sb, ORG, bus=bus), st=_stages(ec))


def _post_pronto(ec, *, formato="reel", aprovar_headline=True, aprovar_roteiro=True):
    h = _headline(ec)
    if aprovar_headline:
        _aprovar_headline(ec, h["id"])
    ro = _roteiro(ec, headline_id=h["id"])
    if aprovar_roteiro:
        _aprovar(ec, ro["id"])
    p = _post(ec, headline_id=h["id"], formato=formato)
    ec.mock_supabase.from_("cs_posts").update({"roteiro_id": ro["id"]}).eq("id", p["id"]).execute()
    return p


def _estado(ec, post_id):
    return ec.mock_supabase.from_("cs_posts").select("*").eq("id", post_id).execute().data[0]


def _eventos(ec, post_id, tipo=None):
    rows = ec.mock_supabase.from_("cs_post_eventos").select("*").eq("post_id", post_id).execute().data
    return [r for r in rows if tipo is None or r["tipo"] == tipo]


def _movimentos(ec, post_id):
    rows = ec.mock_supabase.from_("pipeline_movimentos").select("*").eq("entidade_id", post_id).execute().data
    return sorted(rows, key=lambda r: r.get("created_at") or "")


def _detail(r):
    b = r.json()
    if isinstance(b.get("detail"), dict):
        return b["detail"]
    if isinstance(b.get("error"), dict):
        e = b["error"]
        return {"code": e.get("code"), **(e.get("details") or {})}
    return b


# ── 1. stage model from data ────────────────────────────────────────────────


class TestStageModelIsData:
    def test_the_default_stage_list_is_read_from_the_data_file(self, tmp_path):
        data = tmp_path / "etapas.json"
        data.write_text(json.dumps({"etapas": [{"slug": "a", "label": "A", "cor": "primary", "papel": None},
                                               {"slug": "b", "label": "B", "cor": "warning", "papel": "criacao"}]}))
        got = cfg.carregar_etapas_padrao(data)
        assert [(s.slug, s.papel) for s in got] == [("a", None), ("b", "criacao")]

    def test_the_shipped_list_follows_the_contract_and_gravacao_is_gone(self):
        slugs = [s.slug for s in cfg.ESTEIRA_PADRAO]
        assert slugs == ["ideacao", "headline_roteiro", "criacao", "edicao", "aprovacao_final", "pronto", "postado", "bloqueado_cancelado"]
        assert "Criação" in [s.label for s in cfg.ESTEIRA_PADRAO] and "gravacao" not in slugs
        roles = [s.papel for s in cfg.ESTEIRA_PADRAO if s.papel]
        assert set(roles) <= set(cfg.PIPELINE_ESTEIRA.stage_roles)

    def test_no_stage_slug_literal_lives_in_the_config_module(self):
        src = Path(cfg.__file__).read_text(encoding="utf-8")
        assert 'StageDefault("' not in src and "StageDefault('" not in src

    def test_board_columns_come_from_the_data(self, ec):
        cols = ec.get(f"{BASE}/board").json()["data"]["colunas"]
        assert [c["stage"]["slug"] for c in cols] == [s.slug for s in cfg.ESTEIRA_PADRAO]


class TestRotas:
    def test_reels_and_carrosseis_skip_edicao_avatar_keeps_it_with_captions(self):
        for chave in ("reel_narrado", "carrossel", "estatico"):
            assert cfg.ROLE_EDICAO in ROTAS[chave].etapas_puladas, chave
        assert cfg.ROLE_EDICAO not in ROTAS["avatar"].etapas_puladas
        assert ROTAS["avatar"].subpasso_edicao == "legendas"
        assert ROTAS["reel_narrado"].subpasso_edicao is None

    def test_resolution_by_formato_and_modo(self):
        assert resolver_rota("reel").chave == "reel_narrado"
        assert resolver_rota("reel", "avatar").chave == "avatar"
        assert resolver_rota("carrossel").chave == "carrossel"
        assert resolver_rota("story").chave == "estatico"
        assert resolver_rota("desconhecido") is None

    def test_every_route_key_is_admitted_by_the_database_enum(self):
        sql = next(Path(__file__).resolve().parents[3].joinpath("migrations").glob("*_cs_criacao_posts.sql")).read_text()
        for chave in ROTAS:
            assert f"'{chave}'" in sql, chave


# ── 2. the gate ─────────────────────────────────────────────────────────────


class TestGate:
    def test_headline_sem_aprovacao_nao_entra_em_criacao(self, mv):
        p = _post_pronto(mv.ec, aprovar_headline=False)
        r = _mover(mv.ec, p["id"], mv.st["criacao"]["id"])
        d = _detail(r)
        assert r.status_code == 409 and d["code"] == "pendencias" and d["faltando"] == ["headline_nao_aprovado"]
        assert _estado(mv.ec, p["id"])["etapa_id"] != mv.st["criacao"]["id"]

    def test_roteiro_sem_aprovacao_com_headline_aprovada_continua_recusado(self, mv):
        p = _post_pronto(mv.ec, aprovar_roteiro=False)
        d = _detail(_mover(mv.ec, p["id"], mv.st["criacao"]["id"]))
        assert d["faltando"] == ["roteiro_nao_aprovado"]

    def test_nenhum_aprovado_lista_os_dois(self, mv):
        p = _post_pronto(mv.ec, aprovar_headline=False, aprovar_roteiro=False)
        assert _detail(_mover(mv.ec, p["id"], mv.st["criacao"]["id"]))["faltando"] == ["headline_nao_aprovado", "roteiro_nao_aprovado"]

    def test_headline_reprovada_nao_passa(self, mv):
        h = _headline(mv.ec)
        _aprovar_headline(mv.ec, h["id"], decisao="rejected")
        ro = _roteiro(mv.ec, headline_id=h["id"])
        _aprovar(mv.ec, ro["id"])
        p = _post(mv.ec, headline_id=h["id"])
        mv.sb.from_("cs_posts").update({"roteiro_id": ro["id"]}).eq("id", p["id"]).execute()
        assert _detail(_mover(mv.ec, p["id"], mv.st["criacao"]["id"]))["faltando"] == ["headline_nao_aprovado"]

    def test_ambos_aprovados_passa(self, mv):
        p = _post_pronto(mv.ec)
        assert _mover(mv.ec, p["id"], mv.st["criacao"]["id"]).status_code == 200

    def test_a_recusa_do_mover_do_sistema_e_o_mesmo_corpo_codificado(self, mv):
        p = _post_pronto(mv.ec, aprovar_headline=False)
        with pytest.raises(Exception) as ei:
            mv.mover.entrar_em_criacao(p["id"])
        assert ei.value.status == 409 and ei.value.detail["code"] == "pendencias"
        assert ei.value.detail["faltando"] == ["headline_nao_aprovado"]
        assert "headline_nao_aprovado" not in str(ei.value.detail["detail"])  # the message is pt-BR text, the code is the list
        assert _estado(mv.ec, p["id"]).get("criacao_estado") is None and _movimentos(mv.ec, p["id"]) == []


class TestHeadlineApprovalApi:
    def _com_headline(self, ec):
        h = _headline(ec)
        return h, _post(ec, headline_id=h["id"])

    def test_estado_aprovar_e_reprovar(self, mv):
        ec = mv.ec
        h, p = self._com_headline(ec)
        assert ec.get(f"{BASE}/posts/{p['id']}/headline/aprovacao").json()["data"]["status"] == "none"
        r = ec.post(f"{BASE}/posts/{p['id']}/headline/aprovar")
        assert r.status_code == 200 and r.json()["data"]["status"] == "approved"
        assert ec.get(f"{BASE}/posts/{p['id']}/headline/aprovacao").json()["data"]["status"] == "approved"
        evs = [e["event"] for e in ec.mock_supabase.from_("apr_events").select("*").eq("subject_id", h["id"]).execute().data]
        assert evs == ["submitted", "approved"]

    def test_ja_decidido_e_recusa_codificada(self, mv):
        ec = mv.ec
        h, p = self._com_headline(ec)
        ec.post(f"{BASE}/posts/{p['id']}/headline/aprovar")
        r = ec.post(f"{BASE}/posts/{p['id']}/headline/reprovar", json={"motivo": "x"})
        assert r.status_code == 409 and _detail(r)["code"]

    def test_reprovar(self, mv):
        ec = mv.ec
        h, p = self._com_headline(ec)
        r = ec.post(f"{BASE}/posts/{p['id']}/headline/reprovar", json={"motivo": "fraca"})
        assert r.status_code == 200 and r.json()["data"]["status"] == "rejected" and r.json()["data"]["motivo"] == "fraca"

    def test_post_sem_headline_e_409_codificado(self, mv):
        ec = mv.ec
        p = _post(ec)
        r = ec.post(f"{BASE}/posts/{p['id']}/headline/aprovar")
        assert r.status_code == 409 and _detail(r)["code"] == "sem_headline"

    def test_post_de_outra_org_e_404(self, mv):
        ec = mv.ec
        assert ec.post(f"{BASE}/posts/{uuid.uuid4()}/headline/aprovar").status_code == 404


# ── 3. the system mover ─────────────────────────────────────────────────────


class TestSystemMover:
    def test_reel_entra_em_criacao_enfileirado_com_a_rota(self, mv):
        p = _post_pronto(mv.ec)
        mv.mover.entrar_em_criacao(p["id"])
        row = _estado(mv.ec, p["id"])
        assert row["etapa_id"] == mv.st["criacao"]["id"]
        assert (row["criacao_estado"], row["criacao_rota"]) == (est.NA_FILA, "reel_narrado")
        # the history row names the system actor; the move event + the queue event are intent-named
        (mov,) = _movimentos(mv.ec, p["id"])
        assert mov["responsavel_id"] == SISTEMA_ATOR_ID and mov["motivo"] == "auto:criacao_enfileirada"
        assert [e["tipo"] for e in _eventos(mv.ec, p["id"])] == ["card_movido_automaticamente", "criacao_enfileirada"]
        assert all(e["ator_id"] == SISTEMA_ATOR_ID for e in _eventos(mv.ec, p["id"]))

    def test_entrar_em_criacao_e_idempotente(self, mv):
        p = _post_pronto(mv.ec)
        mv.mover.entrar_em_criacao(p["id"])
        mv.mover.entrar_em_criacao(p["id"])
        assert len(_movimentos(mv.ec, p["id"])) == 1 and len(_eventos(mv.ec, p["id"], "criacao_enfileirada")) == 1

    def test_formato_sem_rota_e_recusa_codificada(self, mv):
        p = _post_pronto(mv.ec, formato="feed")
        mv.sb.from_("cs_posts").update({"formato": "formato_novo"}).eq("id", p["id"]).execute()
        with pytest.raises(CriacaoError) as ei:
            mv.mover.entrar_em_criacao(p["id"])
        assert ei.value.status == 422 and ei.value.detail["code"] == "sem_rota_de_criacao"

    def test_reel_pula_edicao_atravessando_com_rota_pulado(self, mv):
        p = _post_pronto(mv.ec)
        mv.mover.entrar_em_criacao(p["id"])
        mv.mover.iniciar_geracao(p["id"])
        mv.mover.concluir_geracao(p["id"])
        row = _estado(mv.ec, p["id"])
        assert row["etapa_id"] == mv.st["aprovacao_final"]["id"] and row["criacao_estado"] == est.AGUARDANDO_APROVACAO_MIDIA
        motivos = [m["motivo"] for m in _movimentos(mv.ec, p["id"])]
        assert motivos == ["auto:criacao_enfileirada", "rota:pulado", "auto:criacao_concluida"]
        assert _movimentos(mv.ec, p["id"])[1]["para_etapa_id"] == mv.st["edicao"]["id"]

    def test_avatar_para_na_edicao_e_depois_vai_a_aprovacao_final(self, mv):
        p = _post_pronto(mv.ec)
        mv.sb.from_("cs_posts").update({"criacao_rota": "avatar"}).eq("id", p["id"]).execute()
        mv.mover.entrar_em_criacao(p["id"])
        mv.mover.iniciar_geracao(p["id"])
        mv.mover.concluir_geracao(p["id"])
        row = _estado(mv.ec, p["id"])
        assert row["etapa_id"] == mv.st["edicao"]["id"] and row["criacao_estado"] == est.AGUARDANDO_EDICAO
        assert [m["motivo"] for m in _movimentos(mv.ec, p["id"])] == ["auto:criacao_enfileirada", "auto:criacao_concluida"]
        mv.mover.concluir_edicao(p["id"])
        row = _estado(mv.ec, p["id"])
        assert row["etapa_id"] == mv.st["aprovacao_final"]["id"] and row["criacao_estado"] == est.AGUARDANDO_APROVACAO_MIDIA

    def test_falha_fica_em_criacao_com_codigo_visivel(self, mv):
        p = _post_pronto(mv.ec)
        mv.mover.entrar_em_criacao(p["id"])
        mv.mover.iniciar_geracao(p["id"])
        mv.mover.falhar(p["id"], codigo="cota", mensagem="Cota do mês esgotada")
        row = _estado(mv.ec, p["id"])
        assert row["etapa_id"] == mv.st["criacao"]["id"] and (row["criacao_estado"], row["falha_codigo"]) == (est.FALHOU, "cota")
        # a failed card can be queued again (retry) but never skip to the end
        mv.mover.entrar_em_criacao(p["id"])
        assert _estado(mv.ec, p["id"])["criacao_estado"] == est.NA_FILA

    def test_transicao_fora_da_matriz_e_recusa_codificada(self, mv):
        p = _post_pronto(mv.ec)
        mv.mover.entrar_em_criacao(p["id"])
        with pytest.raises(CriacaoError) as ei:
            mv.mover.concluir_geracao(p["id"])  # na_fila -> aguardando_aprovacao_midia is not allowed (must generate first)
        assert ei.value.status == 409 and ei.value.detail["code"] == "transicao_invalida"
        assert _estado(mv.ec, p["id"])["criacao_estado"] == est.NA_FILA

    def test_estado_mudou_por_outro_processo_e_recusa_codificada(self, mv):
        p = _post_pronto(mv.ec)
        mv.mover.entrar_em_criacao(p["id"])
        stale = dict(mv.mover._post(p["id"]))
        mv.mover.iniciar_geracao(p["id"])  # a concurrent mover wins
        with pytest.raises(CriacaoError) as ei:
            mv.mover._estado(stale, est.GERANDO)
        assert ei.value.detail["code"] == "estado_mudou"

    def test_aprovacao_da_midia_leva_a_pronto(self, mv):
        p = _post_pronto(mv.ec)
        for passo in ("entrar_em_criacao", "iniciar_geracao", "concluir_geracao"):
            getattr(mv.mover, passo)(p["id"])
        user = _id()
        mv.mover.decidir_midia(p["id"], aprovada=True, user_id=user)
        row = _estado(mv.ec, p["id"])
        assert row["etapa_id"] == mv.st["pronto"]["id"] and row["criacao_estado"] == est.MIDIA_APROVADA
        assert [e["ator_id"] for e in _eventos(mv.ec, p["id"], "midia_aprovada")] == [user]

    def test_reprovacao_exige_motivo_e_volta_a_criacao_na_fila(self, mv):
        p = _post_pronto(mv.ec)
        for passo in ("entrar_em_criacao", "iniciar_geracao", "concluir_geracao"):
            getattr(mv.mover, passo)(p["id"])
        with pytest.raises(CriacaoError) as ei:
            mv.mover.decidir_midia(p["id"], aprovada=False, user_id=_id())
        assert ei.value.status == 422 and ei.value.detail["code"] == "motivo_obrigatorio"
        mv.mover.decidir_midia(p["id"], aprovada=False, user_id=_id(), motivo="legenda cortada")
        row = _estado(mv.ec, p["id"])
        assert row["etapa_id"] == mv.st["criacao"]["id"] and row["criacao_estado"] == est.NA_FILA
        assert "legenda cortada" in _movimentos(mv.ec, p["id"])[-1]["motivo"]
        assert len(_eventos(mv.ec, p["id"], "midia_reprovada")) == 1 and len(_eventos(mv.ec, p["id"], "criacao_enfileirada")) == 2

    def test_estado_com_evento_proprio_nao_duplica_evento(self, mv):
        p = _post_pronto(mv.ec)
        mv.mover.entrar_em_criacao(p["id"])
        mv.mover.iniciar_geracao(p["id"])  # `gerando` follows the step's own event (cs_criacao_passo_registrar)
        assert [e["tipo"] for e in _eventos(mv.ec, p["id"])].count("passo_iniciado") == 0
        assert est.evento_da_entrada(est.GERANDO) is None
        with pytest.raises(ValueError):
            est.evento_da_entrada(est.REFINANDO)  # the roteiro loop must name its own event, never a silent skip

    def test_a_matriz_so_alcanca_estados_do_enum_do_banco(self):
        sql = next(Path(__file__).resolve().parents[3].joinpath("migrations").glob("*_cs_criacao_posts.sql")).read_text()
        for estado in est.ESTADOS:
            assert f"'{estado}'" in sql, estado
        for de, paras in est.TRANSICOES.items():
            assert de in (None, *est.ESTADOS) and paras <= set(est.ESTADOS)


# ── 4. live stream ──────────────────────────────────────────────────────────


class TestLiveStream:
    def test_a_move_publica_card_moved_depois_do_commit(self, mv):
        p = _post_pronto(mv.ec)
        mv.mover.entrar_em_criacao(p["id"])
        scope = pipeline_scope(ORG, "esteira")
        moved = [f for f in mv.bus.frames if f[1] == "pipeline.card_moved"]
        assert len(moved) == 1 and moved[0][0] == scope
        assert moved[0][2]["card_id"] == p["id"] and moved[0][2]["to_stage_id"] == mv.st["criacao"]["id"]
        assert moved[0][2]["actor"] == SISTEMA_ATOR_ID and moved[0][2]["motivo"] == "auto:criacao_enfileirada"

    def test_traversal_publica_cada_passo_na_ordem(self, mv):
        p = _post_pronto(mv.ec)
        mv.mover.entrar_em_criacao(p["id"])
        mv.mover.iniciar_geracao(p["id"])
        mv.mover.concluir_geracao(p["id"])
        destinos = [f[2]["to_stage_id"] for f in mv.bus.frames if f[1] == "pipeline.card_moved"]
        assert destinos == [mv.st["criacao"]["id"], mv.st["edicao"]["id"], mv.st["aprovacao_final"]["id"]]

    def test_card_state_leva_a_barra_de_progresso(self, mv):
        p = _post_pronto(mv.ec)
        mv.mover.entrar_em_criacao(p["id"])
        mv.mover.progresso(p["id"], passo="tts", rodada=1, progresso=1.7, mensagem="Sintetizando voz (1/3)")
        estados = [f for f in mv.bus.frames if f[1] == "pipeline.card_state"]
        assert estados[-1][0] == pipeline_scope(ORG, "esteira")
        s = estados[-1][2]
        assert s["card_id"] == p["id"] and s["state"]["passo"] == "tts" and s["state"]["progresso"] == 1.0  # clamped
        assert s["state"]["mensagem"] == "Sintetizando voz (1/3)"

    def test_o_mover_humano_tambem_publica(self, mv):
        p = _post_pronto(mv.ec)
        bus = RecBus()
        EsteiraService(mv.sb, ORG, _id(), bus=bus).mover(p["id"], SimpleNamespace(
            para_etapa_id=mv.st["criacao"]["id"], motivo=None, novo_indice=None, permalink=None))
        assert [f[1] for f in bus.frames] == ["pipeline.card_moved"]

    def test_uma_falha_do_barramento_nao_derruba_a_move(self, mv):
        class Quebrado(RecBus):
            async def publish(self, *a, **k):
                raise RuntimeError("redis fora")

        p = _post_pronto(mv.ec)
        CriacaoMover(mv.sb, ORG, bus=Quebrado()).entrar_em_criacao(p["id"])
        assert _estado(mv.ec, p["id"])["etapa_id"] == mv.st["criacao"]["id"]


# ── 5. routes: tier + auth strict 401 + wiring ───────────────────────────────

_NOVAS = [
    ("get", "/posts/{id}/headline/aprovacao", {}),
    ("post", "/posts/{id}/headline/aprovar", {}),
    ("post", "/posts/{id}/headline/reprovar", {"json": {"motivo": "x"}}),
    ("post", "/posts/{id}/criacao/iniciar", {}),
    ("post", "/posts/{id}/midia/aprovar", {}),
    ("post", "/posts/{id}/midia/reprovar", {"json": {"motivo": "x"}}),
    ("post", "/posts/{id}/aprovacoes", {"json": {"alvo": "headline", "decisao": "aprovar"}}),
    ("get", "/stream", {}),
]


class TestRoutes:
    @pytest.mark.parametrize("method,path,kw", _NOVAS)
    def test_unauthenticated_is_exactly_401(self, client, method, path, kw):
        r = getattr(client._tc, method)(BASE + path.replace("{id}", str(uuid.uuid4())), **kw)
        assert r.status_code == 401, (method, path, r.status_code, r.text)

    def test_the_stream_router_is_mounted_and_declared_org_tier(self, client):
        paths = {r.path: r for r in client._tc.app.routes if hasattr(r, "path")}
        assert f"{BASE}/stream" in paths
        from app.modules.media_creation.routers import esteira

        stream = [r for r in esteira.stream_router.routes if getattr(r, "path", "").endswith("/stream")]
        assert stream and stream[0].dependencies is not None

    def test_iniciar_criacao_recusa_sem_aprovacao_e_enfileira_com_aprovacao(self, mv):
        ec = mv.ec
        p = _post_pronto(ec, aprovar_headline=False)
        r = ec.post(f"{BASE}/posts/{p['id']}/criacao/iniciar")
        assert r.status_code == 409 and _detail(r)["faltando"] == ["headline_nao_aprovado"]
        assert ec.post(f"{BASE}/posts/{p['id']}/headline/aprovar").status_code == 200
        r = ec.post(f"{BASE}/posts/{p['id']}/criacao/iniciar")
        assert r.status_code == 202, r.text
        assert r.json()["data"]["etapa_id"] == mv.st["criacao"]["id"]
        assert _estado(ec, p["id"])["criacao_estado"] == est.NA_FILA

    def test_midia_reprovar_sem_motivo_e_422_codificado(self, mv):
        ec = mv.ec
        p = _post_pronto(ec)
        for passo in ("entrar_em_criacao", "iniciar_geracao", "concluir_geracao"):
            getattr(mv.mover, passo)(p["id"])
        r = ec.post(f"{BASE}/posts/{p['id']}/midia/reprovar", json={})
        assert r.status_code == 422 and _detail(r)["code"] == "motivo_obrigatorio"
        assert ec.post(f"{BASE}/posts/{p['id']}/midia/aprovar").status_code == 200
        assert _estado(ec, p["id"])["etapa_id"] == mv.st["pronto"]["id"]


class TestAprovacoesUnificadas:
    """The one call the FE makes (S11): alvo headline | roteiro | midia."""

    def _ap(self, ec, pid, alvo, decisao="aprovar", **kw):
        return ec.post(f"{BASE}/posts/{pid}/aprovacoes", json={"alvo": alvo, "decisao": decisao, **kw})

    def test_headline_e_roteiro_aprovados_aparecem_no_card_e_abrem_o_gate(self, mv):
        ec = mv.ec
        p = _post_pronto(ec, aprovar_headline=False, aprovar_roteiro=False)
        card = ec.get(f"{BASE}/posts/{p['id']}").json()["data"]
        assert (card["headline_aprovada"], card["roteiro_aprovado"], card["midia_aprovada"]) == (False, False, False)
        assert self._ap(ec, p["id"], "headline").json()["data"]["headline_aprovada"] is True
        card = self._ap(ec, p["id"], "roteiro").json()["data"]
        assert (card["headline_aprovada"], card["roteiro_aprovado"]) == (True, True)
        assert ec.post(f"{BASE}/posts/{p['id']}/criacao/iniciar").status_code == 202
        card = ec.get(f"{BASE}/posts/{p['id']}").json()["data"]
        assert card["criacao_estado"] == est.NA_FILA and card["falha_codigo"] is None

    def test_reprovar_sem_motivo_e_422(self, mv):
        p = _post_pronto(mv.ec, aprovar_headline=False)
        assert self._ap(mv.ec, p["id"], "headline", "reprovar").status_code == 422

    def test_midia_por_aqui_leva_a_pronto(self, mv):
        p = _post_pronto(mv.ec)
        for passo in ("entrar_em_criacao", "iniciar_geracao", "concluir_geracao"):
            getattr(mv.mover, passo)(p["id"])
        card = self._ap(mv.ec, p["id"], "midia").json()["data"]
        assert card["midia_aprovada"] is True and card["etapa_id"] == mv.st["pronto"]["id"]

    def test_o_board_leva_os_campos(self, mv):
        _post_pronto(mv.ec)
        cards = [c for col in mv.ec.get(f"{BASE}/board").json()["data"]["colunas"] for c in col["cards"]]
        assert cards and all({"headline_aprovada", "roteiro_aprovado", "midia_aprovada", "criacao_estado", "falha_codigo"} <= set(c) for c in cards)
