"""`POST /api/criacao/ferramentas/{nome}` (criacao-pipeline-contract section 4, S7): the nine READ tools the
Diretor de Criacao (agents) calls back with its org's product token.

Auth matrix = strict `== 401` on the real chain, DI-seam context for 403/200 (same as Julia's tools).
Fixtures plant a second org's rows that no tool may ever return."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from noctusai_lib.api.auth.session import AuthContext
from noctusai_lib.testing import MockSupabaseClient

_ORG = UUID("00000000-0000-4000-8000-0000000000aa")
_OTHER = UUID("00000000-0000-4000-8000-0000000000bb")
_SCOPE = "social-wiring:criacao-tools"
URL = "/api/criacao/ferramentas"
MARCA = "10000000-0000-4000-8000-000000000001"
MARCA_OUTRA = "10000000-0000-4000-8000-000000000002"
TIPO_HOOK, TIPO_CTA = "20000000-0000-4000-8000-000000000001", "20000000-0000-4000-8000-000000000002"
PERFIL_A, PERFIL_B = "30000000-0000-4000-8000-000000000001", "30000000-0000-4000-8000-000000000002"
SEGREDO = "PLANTED-OTHER-ORG"
_AGORA = datetime.now(timezone.utc)


def _iso(dias: float) -> str:
    return (_AGORA - timedelta(days=dias)).isoformat()


@pytest.fixture
def db():
    d = MockSupabaseClient()
    d.set_table_data("marcas", [{"id": MARCA, "org_id": str(_ORG)}, {"id": MARCA_OUTRA, "org_id": str(_OTHER)}])
    d.set_table_data("cs_marca_perfil", [
        {"marca_id": MARCA, "org_id": str(_ORG), "bio": "Psicóloga.", "apresentacao_magnetica": "Eu ajudo...",
         "ctas": "Siga para mais", "nichos": [1], "profissoes": [2]},
        {"marca_id": MARCA_OUTRA, "org_id": str(_OTHER), "bio": SEGREDO, "apresentacao_magnetica": "", "ctas": "",
         "nichos": [], "profissoes": []},
    ])
    d.set_table_data("mc_brand_kits", [
        {"id": str(uuid4()), "org_id": str(_ORG), "marca_id": MARCA, "name": "Kit", "persona": "calma", "design_system": "",
         "brand_book": "", "tokens": {"cor": "#fff"}, "default_lang": "pt-BR", "created_at": _iso(5)},
        {"id": str(uuid4()), "org_id": str(_OTHER), "marca_id": MARCA_OUTRA, "name": SEGREDO, "persona": "", "design_system": "",
         "brand_book": "", "tokens": None, "default_lang": "pt-BR", "created_at": _iso(5)},
    ])
    d.set_table_data("cs_memorias", [
        {"id": str(uuid4()), "org_id": str(_ORG), "marca_id": MARCA, "texto": "Evitar jargão", "created_at": _iso(3)},
        {"id": str(uuid4()), "org_id": str(_OTHER), "marca_id": MARCA_OUTRA, "texto": SEGREDO, "created_at": _iso(3)},
    ])
    d.set_table_data("cs_brains", [
        {"id": str(uuid4()), "org_id": str(_ORG), "marca_id": MARCA, "kind": "sistema", "template_slug": "metodo-do-especialista",
         "name": "Método", "content": "Passo 1...", "content_version": 2, "synthesis_status": "idle", "synthesized_at": _iso(2)},
        {"id": str(uuid4()), "org_id": str(_ORG), "marca_id": MARCA, "kind": "sistema", "template_slug": "nucleo-de-influencia",
         "name": "Núcleo", "content": "", "content_version": 0, "synthesis_status": "idle", "synthesized_at": None},
        {"id": str(uuid4()), "org_id": str(_OTHER), "marca_id": MARCA_OUTRA, "kind": "custom", "template_slug": None,
         "name": SEGREDO, "content": SEGREDO, "content_version": 1, "synthesis_status": "idle", "synthesized_at": None},
    ])
    d.set_table_data("cs_perfis_monitorados", [
        {"id": PERFIL_A, "org_id": str(_ORG), "handle": "criadora.a"}, {"id": PERFIL_B, "org_id": str(_ORG), "handle": "criador.b"},
    ])
    d.set_table_data("cs_estruturas", [
        {"id": "40000000-0000-4000-8000-000000000001", "codigo": 101, "perfil_id": PERFIL_A, "formato": "reels",
         "objetivos": ["alcance"], "formula_headline": "Erro comum de ansiedade que ninguém conta", "status": "ativa"},
        {"id": "40000000-0000-4000-8000-000000000002", "codigo": 102, "perfil_id": PERFIL_B, "formato": "reels",
         "objetivos": ["venda", "autoridade"], "formula_headline": "Três passos para vender mais", "status": "ativa"},
        {"id": "40000000-0000-4000-8000-000000000003", "codigo": 103, "perfil_id": PERFIL_B, "formato": "carrossel",
         "objetivos": ["alcance"], "formula_headline": "Carrossel de ansiedade", "status": "ativa"},
        {"id": "40000000-0000-4000-8000-000000000004", "codigo": 104, "perfil_id": PERFIL_B, "formato": "reels",
         "objetivos": ["alcance"], "formula_headline": "Rascunho de ansiedade", "status": "rascunho"},
    ])
    d.set_table_data("cs_estrutura_tipos_bloco", [
        {"id": TIPO_HOOK, "nome": "Gancho", "instrucao_referencia": "Prenda a atenção."},
        {"id": TIPO_CTA, "nome": "CTA Salvar", "instrucao_referencia": "Peça para salvar."},
    ])
    d.set_table_data("cs_estrutura_blocos", [
        {"id": str(uuid4()), "estrutura_id": "40000000-0000-4000-8000-000000000001", "ordem": 1, "tipo_id": TIPO_HOOK,
         "nome": "Abertura", "tempo": "0-3s", "instrucao": None, "nota": None, "repeticoes": 1},
        {"id": str(uuid4()), "estrutura_id": "40000000-0000-4000-8000-000000000001", "ordem": 2, "tipo_id": TIPO_CTA,
         "nome": "Fecho", "tempo": "28-30s", "instrucao": "Salve para rever.", "nota": None, "repeticoes": 1},
        {"id": str(uuid4()), "estrutura_id": "40000000-0000-4000-8000-000000000002", "ordem": 1, "tipo_id": TIPO_HOOK,
         "nome": "Abertura", "tempo": "0-3s", "instrucao": "x", "nota": None, "repeticoes": 1},
    ])
    d.set_table_data("cs_biblioteca_referencias", [
        {"id": str(uuid4()), "org_id": str(_ORG), "marca_id": MARCA, "modo": "perfil", "perfil_id": PERFIL_B, "viral_id": None},
    ])
    d.set_table_data("cs_research_items", [
        {"id": str(uuid4()), "org_id": str(_ORG), "marca_id": MARCA, "variable_slug": "dores", "content": "Insônia crônica",
         "status": "approved", "source_ref": {"url": "https://exemplo.test/a"}, "plays": 10, "created_at": _iso(1)},
        {"id": str(uuid4()), "org_id": str(_ORG), "marca_id": MARCA, "variable_slug": "dores", "content": "Culpa materna",
         "status": "approved", "source_ref": None, "plays": None, "created_at": _iso(2)},
        {"id": str(uuid4()), "org_id": str(_ORG), "marca_id": MARCA, "variable_slug": "dores", "content": "Pendente",
         "status": "pending", "source_ref": None, "plays": None, "created_at": _iso(1)},
        {"id": str(uuid4()), "org_id": str(_OTHER), "marca_id": MARCA_OUTRA, "variable_slug": "dores", "content": SEGREDO,
         "status": "approved", "source_ref": None, "plays": None, "created_at": _iso(1)},
    ])
    d.set_table_data("cs_virais", [
        {"id": str(uuid4()), "org_id": str(_ORG), "perfil_id": PERFIL_B, "codigo": 7, "permalink": "https://ig.test/p/7",
         "media_product_type": "REELS", "publicado_em": _iso(10), "likes": 100, "comments": 5, "views": 9000, "duracao_s": 30,
         "score_viral": 3.2, "e_viral": True, "gancho": "Você erra isso", "blueprint": "bp", "gatilho": "crenca"},
        {"id": str(uuid4()), "org_id": str(_ORG), "perfil_id": PERFIL_B, "codigo": 8, "permalink": "https://ig.test/p/8",
         "media_product_type": "REELS", "publicado_em": _iso(11), "likes": 1, "comments": 0, "views": 10, "duracao_s": 20,
         "score_viral": 0.1, "e_viral": False, "gancho": None, "blueprint": None, "gatilho": None},
        {"id": str(uuid4()), "org_id": str(_OTHER), "perfil_id": PERFIL_B, "codigo": 9, "permalink": SEGREDO,
         "media_product_type": "REELS", "publicado_em": _iso(1), "likes": 1, "comments": 0, "views": 1, "duracao_s": 20,
         "score_viral": 9.9, "e_viral": True, "gancho": SEGREDO, "blueprint": None, "gatilho": None},
    ])
    d.set_table_data("cs_posts", [
        {"id": str(uuid4()), "org_id": str(_ORG), "marca_id": MARCA, "titulo": "Post A", "formato": "reel",
         "postado_em": _iso(4), "permalink": "https://instagram.com/p/a"},
        {"id": str(uuid4()), "org_id": str(_ORG), "marca_id": MARCA, "titulo": "Antigo", "formato": "reel",
         "postado_em": _iso(100), "permalink": "https://instagram.com/p/b"},
        {"id": str(uuid4()), "org_id": str(_OTHER), "marca_id": MARCA_OUTRA, "titulo": SEGREDO, "formato": "reel",
         "postado_em": _iso(1), "permalink": None},
    ])
    d.set_table_data("ig_metric_snapshots", [
        {"id": str(uuid4()), "org_id": str(_ORG), "captured_at": _iso(20), "followers_count": 100, "reach": 50, "profile_views": 3},
        {"id": str(uuid4()), "org_id": str(_ORG), "captured_at": _iso(1), "followers_count": 130, "reach": 70, "profile_views": 4},
        {"id": str(uuid4()), "org_id": str(_OTHER), "captured_at": _iso(1), "followers_count": 999, "reach": 999, "profile_views": 9},
    ])
    d.set_table_data("transcricoes", [])
    d.set_table_data("cs_treinamentos", [
        {"id": str(uuid4()), "ordem": 2, "titulo": "B", "descricao": "d", "video_url": "https://v.test/b", "ativo": True},
        {"id": str(uuid4()), "ordem": 1, "titulo": "A", "descricao": "d", "video_url": "https://v.test/a", "ativo": True},
        {"id": str(uuid4()), "ordem": 3, "titulo": "Off", "descricao": "d", "video_url": None, "ativo": False},
    ])
    return d


@pytest.fixture
def tools(client, db):
    from app.dependencies import get_auth_context
    from app.main import app
    from app.routers.criacao_ferramentas_router import get_criacao_client

    app.dependency_overrides[get_criacao_client] = lambda: db
    prev = app.dependency_overrides.get(get_auth_context)

    class T:
        raw = client.raw()

        def as_ctx(self, ctx):
            app.dependency_overrides[get_auth_context] = lambda: ctx

        def post(self, nome, body=None):
            return self.raw.post(f"{URL}/{nome}", json=body if body is not None else {})

    yield T()
    app.dependency_overrides.pop(get_criacao_client, None)
    if prev is None:
        app.dependency_overrides.pop(get_auth_context, None)
    else:
        app.dependency_overrides[get_auth_context] = prev


def _product(*, scopes=(_SCOPE,), issuer="agents", org=_ORG):
    return AuthContext(org_id=org, caller_kind="product", user_id=None, scopes=list(scopes),
                       raw_token="t", api_token_id=uuid4(), issuer=issuer)


@pytest.fixture
def ok(tools):
    tools.as_ctx(_product())
    return tools


class TestAuthMatrix:
    def test_no_credential_is_exactly_401(self, tools):
        assert tools.post("contexto_marca", {"marca_id": MARCA}).status_code == 401

    def test_unknown_tool_without_credentials_is_401_not_404(self, tools):
        assert tools.post("nao_existe").status_code == 401

    def test_a_human_session_is_403_product_required(self, tools):
        tools.as_ctx(AuthContext(org_id=_ORG, caller_kind="user", user_id=uuid4(), scopes=[], raw_token="s", api_token_id=None))
        r = tools.post("contexto_marca", {"marca_id": MARCA})
        assert r.status_code == 403 and r.json()["code"] == "product_required"

    def test_wrong_scope_is_403_scope_missing(self, tools):
        tools.as_ctx(_product(scopes=["social-wiring:lais-tools"]))  # Julia's scope never opens the criacao tools
        r = tools.post("contexto_marca", {"marca_id": MARCA})
        assert r.status_code == 403 and r.json()["code"] == "scope_missing"

    def test_wrong_issuer_is_403(self, tools):
        tools.as_ctx(_product(issuer="outro"))
        r = tools.post("contexto_marca", {"marca_id": MARCA})
        assert r.status_code == 403 and r.json()["code"] == "issuer_not_allowed"


class TestEnvelope:
    def test_unknown_tool_404(self, ok):
        r = ok.post("apagar_tudo")
        assert r.status_code == 404 and r.json()["error"]["code"] == "ferramenta_desconhecida"

    @pytest.mark.parametrize("nome,corpo", [
        ("contexto_marca", {}),
        ("contexto_marca", {"marca_id": "nao-uuid"}),
        ("contexto_marca", {"marca_id": MARCA, "org_id": str(_OTHER)}),  # a body can never pick the org
        ("estruturas_buscar", {"marca_id": MARCA}),
        ("estruturas_buscar", {"marca_id": MARCA, "formato": "reels", "limite": 21}),
        ("estruturas_buscar", {"marca_id": MARCA, "formato": "reel"}),
        ("estrutura_detalhe", {"codigo": 0}),
        ("desempenho", {"marca_id": MARCA, "janela_dias": 0}),
    ])
    def test_bad_body_is_422_invalid_field(self, ok, nome, corpo):
        r = ok.post(nome, corpo)
        assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_field"

    def test_success_envelope_is_data(self, ok):
        assert set(ok.post("treinamentos", {"marca_id": MARCA}).json()) == {"data"}


class TestCrossOrg:
    @pytest.mark.parametrize("nome", ["contexto_marca", "cerebros", "pesquisas", "virais", "desempenho", "voz_amostras", "treinamentos"])
    def test_another_orgs_marca_is_404(self, ok, nome):
        r = ok.post(nome, {"marca_id": MARCA_OUTRA})
        assert r.status_code == 404 and r.json()["error"]["code"] == "marca_nao_encontrada"

    def test_estruturas_buscar_other_org_marca_404(self, ok):
        assert ok.post("estruturas_buscar", {"marca_id": MARCA_OUTRA, "formato": "reels"}).status_code == 404

    def test_the_other_org_token_cannot_read_this_orgs_marca(self, tools):
        tools.as_ctx(_product(org=_OTHER))
        assert tools.post("contexto_marca", {"marca_id": MARCA}).status_code == 404

    @pytest.mark.parametrize("nome,corpo", [
        ("contexto_marca", {"marca_id": MARCA}), ("cerebros", {"marca_id": MARCA}), ("pesquisas", {"marca_id": MARCA}),
        ("virais", {"marca_id": MARCA}), ("desempenho", {"marca_id": MARCA}),
    ])
    def test_no_planted_secret_ever_leaks(self, ok, nome, corpo):
        assert SEGREDO not in ok.post(nome, corpo).text


class TestShapes:
    def test_contexto_marca(self, ok):
        d = ok.post("contexto_marca", {"marca_id": MARCA}).json()["data"]
        assert d["perfil"]["apresentacao_magnetica"] == "Eu ajudo..." and d["perfil"]["ctas"] == "Siga para mais"
        assert d["perfil"]["nichos"] == [1] and d["brand_kit"]["name"] == "Kit" and d["memorias"] == ["Evitar jargão"]

    def test_cerebros_reports_empty_brains(self, ok):
        d = ok.post("cerebros", {"marca_id": MARCA}).json()["data"]
        assert {c["nome"]: c["vazio"] for c in d["cerebros"]} == {"Método": False, "Núcleo": True}
        assert d["vazios"] == ["Núcleo"]

    def test_cerebros_filter_by_tipo(self, ok):
        d = ok.post("cerebros", {"marca_id": MARCA, "tipos": ["metodo-do-especialista"]}).json()["data"]
        assert [c["nome"] for c in d["cerebros"]] == ["Método"]

    def test_estruturas_buscar_filters_ranks_and_types_blocks(self, ok):
        d = ok.post("estruturas_buscar", {"marca_id": MARCA, "formato": "reels", "texto": "ansiedade"}).json()["data"]
        assert [e["codigo"] for e in d["estruturas"]] == [101, 102]  # active + reels only; text match first
        assert d["estruturas"][0]["blocos"][1]["eh_cta"] is True and d["estruturas"][0]["blocos"][0]["eh_cta"] is False
        assert d["estruturas"][0]["blocos"][0]["instrucao"] == "Prenda a atenção."  # falls back to the type's instruction
        assert d["estruturas"][0]["perfil"] == "criadora.a"

    def test_estruturas_buscar_objetivo_and_limite(self, ok):
        d = ok.post("estruturas_buscar", {"marca_id": MARCA, "formato": "reels", "objetivo": "venda", "limite": 1}).json()["data"]
        assert [e["codigo"] for e in d["estruturas"]] == [102]

    def test_estruturas_buscar_brand_profile_boost(self, ok):
        d = ok.post("estruturas_buscar", {"marca_id": MARCA, "formato": "reels"}).json()["data"]
        assert [e["codigo"] for e in d["estruturas"]] == [102, 101]  # PERFIL_B is in the brand's library selection

    def test_estrutura_detalhe(self, ok):
        d = ok.post("estrutura_detalhe", {"codigo": 101}).json()["data"]
        assert d["codigo"] == 101 and len(d["blocos"]) == 2

    def test_estrutura_detalhe_draft_or_missing_404(self, ok):
        assert ok.post("estrutura_detalhe", {"codigo": 104}).status_code == 404
        assert ok.post("estrutura_detalhe", {"codigo": 999}).status_code == 404

    def test_pesquisas_only_approved_with_url_and_tema(self, ok):
        d = ok.post("pesquisas", {"marca_id": MARCA}).json()["data"]["pesquisas"]
        assert {p["conteudo"] for p in d} == {"Insônia crônica", "Culpa materna"}
        assert next(p for p in d if p["conteudo"] == "Insônia crônica")["url"] == "https://exemplo.test/a"
        d2 = ok.post("pesquisas", {"marca_id": MARCA, "tema": "culpa"}).json()["data"]["pesquisas"]
        assert [p["conteudo"] for p in d2] == ["Culpa materna"]

    def test_virais_only_viral_from_the_brands_library(self, ok):
        d = ok.post("virais", {"marca_id": MARCA}).json()["data"]["virais"]
        assert [v["codigo"] for v in d] == [7] and d[0]["metricas"]["views"] == 9000 and d[0]["gancho"] == "Você erra isso"

    def test_desempenho_says_when_there_are_no_per_post_metrics(self, ok):
        d = ok.post("desempenho", {"marca_id": MARCA, "janela_dias": 30}).json()["data"]
        assert [p["titulo"] for p in d["posts_publicados"]] == ["Post A"]
        assert d["metricas_por_post"]["disponivel"] is False
        assert d["conta"]["seguidores_inicio"] == 100 and d["conta"]["seguidores_fim"] == 130 and d["conta"]["alcance_total"] == 120

    def test_desempenho_without_snapshots_warns(self, ok, db):
        db.set_table_data("ig_metric_snapshots", [])
        d = ok.post("desempenho", {"marca_id": MARCA}).json()["data"]
        assert d["conta"] is None and d["avisos"] == ["sem_snapshots_da_conta_na_janela"]

    def test_voz_amostras_empty_with_reason(self, ok):
        assert ok.post("voz_amostras", {"marca_id": MARCA}).json()["data"] == {"amostras": [], "motivo": "sem_transcricoes_da_marca"}

    def test_voz_amostras_with_transcript(self, ok, db):
        db.set_table_data("transcricoes", [{
            "org_id": str(_ORG), "contexto_tipo": "marca", "contexto_ref": MARCA, "status": "concluida",
            "texto": " ".join(["palavra"] * 120), "duracao_s": 60, "concluido_em": _iso(1)}])
        a = ok.post("voz_amostras", {"marca_id": MARCA, "n": 3}).json()["data"]["amostras"]
        assert len(a) == 1 and a[0]["palavras"] == 120 and a[0]["wpm"] == 120.0

    def test_treinamentos_active_in_order(self, ok):
        d = ok.post("treinamentos", {"marca_id": MARCA}).json()["data"]["treinamentos"]
        assert [t["titulo"] for t in d] == ["A", "B"]
