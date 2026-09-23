"""Orçamentos, Produtos e Serviços and Contratos — wave-2 slice A.

The rules that carry the weight:
  * every number is SERVER-computed — recurrence (popcount × qtd/dia × 4),
    subtotals, totals, cost and margin; a client cannot send a total;
  * accepting runs EXACTLY the funnel's fechado transition (negócio ganho in
    the `fechado` stage, Cliente created, siblings substituido) and then fills
    the next 30 days of the calendar with pautas — idempotently;
  * a closed proposal (aceito/recusado/substituido/expirado) is frozen (409
    `orcamento_bloqueado`), and past `validade` reads as `expirado`;
  * the PDFs are real documents that never carry the agency's internal cost;
  * a physical contract is signed by hand (lines + "N vias"), a digital one is
    NOT activatable by hand.

Everything runs on the shared `igig` mock (`crm_api`): the orçamento code and
the funnel service it reuses read and write the same rows, as in production.
Storage is the seed's `FakeStorageBackend`, injected through the routers'
`get_storage` dependency.
"""
from datetime import date, timedelta

import anyio
import fitz
import pytest
from noctusai_lib.integrations.storage import FakeStorageBackend

from app.dependencies import coerce_org_uuid
from app.services.orcamentos import hoje_local

ORG = str(coerce_org_uuid("test-org-123"))
BUCKET = "igig"
SEG, TER, QUA, QUI, SEX, SAB, DOM = 1, 2, 4, 8, 16, 32, 64


# ── Fixtures ────────────────────────────────────────────────────────
@pytest.fixture
def storage() -> FakeStorageBackend:
    return FakeStorageBackend()


@pytest.fixture
def api(crm_api, core_db, storage):
    from app.main import app
    from app.storage import get_storage

    app.dependency_overrides[get_storage] = lambda: storage
    core_db.table("organizations").insert({"id": ORG, "nome": "Agência Aurora"}).execute()
    yield crm_api
    app.dependency_overrides.pop(get_storage, None)


@pytest.fixture
def etapas(api) -> dict[str, dict]:
    resp = api.get("/api/comercial/pipeline/stages")
    assert resp.status_code == 200, resp.text
    return {s["slug"]: s for s in resp.json()["data"]}


@pytest.fixture
def negocio(api, etapas) -> dict:
    resp = api.post("/api/comercial/negocios", json={
        "lead": {"nome": "João", "empresa": "Padaria Sol", "email": "joao@sol.com"},
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


@pytest.fixture
def catalogo(api) -> dict[str, dict]:
    resp = api.get("/api/produtos-servicos")
    assert resp.status_code == 200, resp.text
    return {p["nome"]: p for p in resp.json()["data"]}


@pytest.fixture
def equipe(igig_db):
    """One professional at R$100/h — the custo/hora spine's input."""
    funcao = igig_db.table("funcao").insert(
        {"org_id": ORG, "nome": "designer", "custo_hora_padrao": 100.0}
    ).execute().data[0]
    igig_db.table("profissional").insert(
        {"org_id": ORG, "nome": "Ana", "funcao_id": funcao["id"], "ativo": True}
    ).execute()


def _item_post(catalogo, *, dias=SEG | QUA | SEX, qtd=2):
    p = catalogo["Post feed"]
    return {"produto_servico_id": p["id"], "secao": "criacao_conteudo", "descricao": "Post feed",
            "preco_unitario": 80, "recorrente": True, "dias_semana": dias, "qtd_por_dia": qtd}


def _item_gestao(catalogo):
    p = catalogo["Gestão de DMs"]
    return {"produto_servico_id": p["id"], "secao": "gestao_conta", "descricao": "Gestão de DMs",
            "preco_unitario": 500, "quantidade": 1}


def _criar(api, negocio, itens, **extra):
    resp = api.post("/api/orcamentos", json={"negocio_id": negocio["id"], "itens": itens, **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def _linhas(igig_db, tabela, **filtros):
    return [r for r in igig_db.table(tabela)._data
            if all(r.get(k) == v for k, v in filtros.items())]


def _pdf_texto(storage: FakeStorageBackend, chave: str) -> str:
    async def _ler():
        return await storage.get(bucket=BUCKET, key=chave)

    blob = anyio.run(_ler)
    assert blob is not None, f"nothing stored at {chave}"
    assert blob.data.startswith(b"%PDF")
    return "\n".join(p.get_text() for p in fitz.open(stream=blob.data, filetype="pdf"))


# ── Produtos e Serviços ─────────────────────────────────────────────
class TestProdutosServicos:
    def test_requires_auth(self, api):
        assert api.raw().get("/api/produtos-servicos").status_code == 401

    def test_first_read_seeds_the_owners_examples(self, catalogo):
        assert catalogo["Gestão de conteúdo"]["preco_base"] == 500.0
        assert catalogo["Gestão de conteúdo"]["secao"] == "gestao_conta"
        assert catalogo["Gestão de DMs"]["preco_base"] == 500.0
        for nome, formato in (("Post feed", "feed"), ("Carrossel", "carrossel"),
                              ("Reels", "reels"), ("Stories", "story")):
            assert catalogo[nome]["secao"] == "criacao_conteudo"
            assert catalogo[nome]["formato"] == formato
            assert catalogo[nome]["preco_base"] > 0 and catalogo[nome]["horas_estimadas"] > 0

    def test_seeding_happens_once(self, api, catalogo, igig_db):
        api.get("/api/produtos-servicos")
        assert len(_linhas(igig_db, "produto_servico", org_id=ORG)) == len(catalogo)

    def test_a_deactivated_catalogue_is_not_reseeded(self, api, catalogo, igig_db):
        for p in catalogo.values():
            api.patch(f"/api/produtos-servicos/{p['id']}", json={"ativo": False})
        assert api.get("/api/produtos-servicos?ativo=true").json()["data"] == []
        assert len(_linhas(igig_db, "produto_servico", org_id=ORG)) == len(catalogo)

    def test_filters_by_secao(self, api, catalogo):
        dados = api.get("/api/produtos-servicos?secao=gestao_conta").json()["data"]
        assert {p["nome"] for p in dados} == {"Gestão de conteúdo", "Gestão de DMs"}

    def test_create(self, api, catalogo):
        resp = api.post("/api/produtos-servicos", json={
            "secao": "criacao_conteudo", "nome": "Vídeo YouTube", "preco_base": 900,
            "horas_estimadas": 10, "formato": "video",
        })
        assert resp.status_code == 201
        assert resp.json()["data"]["formato"] == "video"

    def test_duplicate_name_in_section_is_409(self, api, catalogo):
        resp = api.post("/api/produtos-servicos", json={"secao": "criacao_conteudo", "nome": "Reels"})
        assert resp.status_code == 409
        assert resp.json()["code"] == "produto_duplicado"

    def test_unknown_field_is_422(self, api, catalogo):
        resp = api.post("/api/produtos-servicos",
                        json={"secao": "gestao_conta", "nome": "X", "margem": 50})
        assert resp.status_code == 422

    def test_patch(self, api, catalogo):
        resp = api.patch(f"/api/produtos-servicos/{catalogo['Reels']['id']}",
                         json={"preco_base": 300})
        assert resp.status_code == 200
        assert resp.json()["data"]["preco_base"] == 300.0
        assert resp.json()["data"]["nome"] == "Reels"

    def test_patch_unknown_is_404(self, api, catalogo):
        assert api.patch("/api/produtos-servicos/nao-existe",
                         json={"preco_base": 1}).status_code == 404

    def test_delete_unreferenced_is_hard(self, api, catalogo, igig_db):
        resp = api.delete(f"/api/produtos-servicos/{catalogo['Stories']['id']}")
        assert resp.status_code == 200
        assert resp.json()["data"]["removido"] is True
        assert not _linhas(igig_db, "produto_servico", id=catalogo["Stories"]["id"])

    def test_delete_referenced_is_soft(self, api, catalogo, negocio, igig_db):
        _criar(api, negocio, [_item_post(catalogo)])
        resp = api.delete(f"/api/produtos-servicos/{catalogo['Post feed']['id']}")
        assert resp.status_code == 200
        assert resp.json()["data"] == {
            "id": catalogo["Post feed"]["id"], "removido": False, "desativado": True,
        }
        linha = _linhas(igig_db, "produto_servico", id=catalogo["Post feed"]["id"])[0]
        assert linha["ativo"] is False


# ── Calcular ────────────────────────────────────────────────────────
class TestCalcular:
    def test_requires_auth(self, api):
        assert api.raw().post("/api/orcamentos/calcular", json={"itens": []}).status_code == 401

    def test_recurrence_math(self, api, catalogo, equipe):
        """Seg+Qua+Sex × 2/dia × 4 semanas = 24 posts/mês."""
        resp = api.post("/api/orcamentos/calcular",
                        json={"itens": [_item_post(catalogo), _item_gestao(catalogo)]})
        assert resp.status_code == 200, resp.text
        dados = resp.json()["data"]
        post, gestao = dados["itens"]
        assert post["quantidade_mensal"] == 24
        assert post["subtotal"] == 24 * 80
        assert gestao["quantidade_mensal"] == 1
        assert dados["subtotal_criacao"] == 1920.0
        assert dados["subtotal_gestao"] == 500.0
        assert dados["total_mensal"] == 2420.0

    def test_cost_and_margin_from_the_custo_hora_spine(self, api, catalogo, equipe):
        """Post feed = 2h; 24 posts = 48h; + DMs 10h × 1 = 58h at R$100/h."""
        dados = api.post("/api/orcamentos/calcular",
                         json={"itens": [_item_post(catalogo), _item_gestao(catalogo)]}).json()["data"]
        assert dados["horas_estimadas"] == 58.0
        assert dados["custo_estimado"] == 5800.0
        assert dados["margem_estimada"] == round((2420 - 5800) / 2420 * 100, 2)
        assert dados["margem_estimada"] < 0, "below cost is SHOWN, never clamped"
        assert dados["alertas"] == []

    def test_discount_reduces_total(self, api, catalogo, equipe):
        dados = api.post("/api/orcamentos/calcular", json={
            "itens": [_item_gestao(catalogo)], "desconto": 100,
        }).json()["data"]
        assert dados["desconto"] == 100.0
        assert dados["total_mensal"] == 400.0

    def test_without_team_rates_it_warns(self, api, catalogo):
        dados = api.post("/api/orcamentos/calcular",
                         json={"itens": [_item_gestao(catalogo)]}).json()["data"]
        assert dados["custo_estimado"] == 0.0
        assert dados["alertas"] and "NÃO devem ser usados" in dados["alertas"][-1]

    def test_professionals_without_a_rate_are_excluded_not_zeroed(
        self, api, catalogo, equipe, igig_db
    ):
        igig_db.table("profissional").insert(
            {"org_id": ORG, "nome": "Sem rate", "ativo": True}
        ).execute()
        dados = api.post("/api/orcamentos/calcular",
                         json={"itens": [_item_gestao(catalogo)]}).json()["data"]
        assert dados["custo_hora_medio"] == 100.0
        assert any("excluídos" in a for a in dados["alertas"])

    def test_recurring_item_without_weekday_is_422(self, api, catalogo):
        item = {**_item_post(catalogo), "dias_semana": 0}
        resp = api.post("/api/orcamentos/calcular", json={"itens": [item]})
        assert resp.status_code == 422
        assert resp.json()["code"] == "recorrencia_invalida"

    def test_discount_above_subtotal_is_422(self, api, catalogo):
        resp = api.post("/api/orcamentos/calcular",
                        json={"itens": [_item_gestao(catalogo)], "desconto": 501})
        assert resp.status_code == 422
        assert resp.json()["code"] == "desconto_invalido"

    def test_unknown_product_is_422(self, api, catalogo):
        item = {**_item_gestao(catalogo), "produto_servico_id": "nao-existe"}
        resp = api.post("/api/orcamentos/calcular", json={"itens": [item]})
        assert resp.status_code == 422
        assert resp.json()["code"] == "produto_invalido"

    def test_client_cannot_send_a_subtotal(self, api, catalogo):
        item = {**_item_gestao(catalogo), "subtotal": 1}
        assert api.post("/api/orcamentos/calcular", json={"itens": [item]}).status_code == 422

    def test_writes_nothing(self, api, catalogo, igig_db):
        api.post("/api/orcamentos/calcular", json={"itens": [_item_gestao(catalogo)]})
        assert _linhas(igig_db, "orcamento") == []


# ── CRUD + versões ──────────────────────────────────────────────────
class TestOrcamentoCrud:
    def test_requires_auth(self, api):
        assert api.raw().get("/api/orcamentos").status_code == 401
        assert api.raw().post("/api/orcamentos", json={"negocio_id": "x"}).status_code == 401

    def test_create_stores_server_computed_totals_and_items(
        self, api, catalogo, negocio, equipe, igig_db
    ):
        orc = _criar(api, negocio, [_item_post(catalogo), _item_gestao(catalogo)],
                     desconto=20, validade=(hoje_local() + timedelta(days=10)).isoformat())
        assert orc["versao"] == 1 and orc["status"] == "rascunho"
        assert orc["total_mensal"] == 2400.0
        assert orc["custo_estimado"] == 5800.0
        assert [i["quantidade_mensal"] for i in orc["itens"]] == [24, 1]
        assert orc["lead"]["nome"] == "João" and orc["lead"]["email"] == "joao@sol.com"
        assert orc["negocio"]["id"] == negocio["id"]
        assert orc["lead_id"] == negocio["lead_id"]
        assert orc["limites_escopo"]["revisoes_incluidas"] == 2
        assert len(_linhas(igig_db, "orcamento_item", orcamento_id=orc["id"])) == 2

    def test_versao_is_max_plus_one_per_negocio(self, api, catalogo, negocio):
        _criar(api, negocio, [_item_gestao(catalogo)])
        segundo = _criar(api, negocio, [_item_gestao(catalogo)])
        assert segundo["versao"] == 2

    def test_unknown_negocio_is_404(self, api, catalogo):
        resp = api.post("/api/orcamentos", json={"negocio_id": "nao-existe", "itens": []})
        assert resp.status_code == 404

    def test_lost_negocio_refuses_new_orcamento(self, api, catalogo, negocio):
        api.post(f"/api/comercial/negocios/{negocio['id']}/perder", json={"motivo": "preço"})
        resp = api.post("/api/orcamentos", json={"negocio_id": negocio["id"], "itens": []})
        assert resp.status_code == 409
        assert resp.json()["code"] == "negocio_encerrado"

    def test_get_by_id(self, api, catalogo, negocio):
        orc = _criar(api, negocio, [_item_gestao(catalogo)])
        resp = api.get(f"/api/orcamentos/{orc['id']}")
        assert resp.status_code == 200
        assert resp.json()["data"]["itens"][0]["descricao"] == "Gestão de DMs"

    def test_unknown_id_is_404(self, api):
        assert api.get("/api/orcamentos/nao-existe").status_code == 404

    def test_list_tabs_and_filters(self, api, catalogo, negocio, etapas):
        a = _criar(api, negocio, [_item_gestao(catalogo)], titulo="Plano Básico")
        b = _criar(api, negocio, [_item_gestao(catalogo)], titulo="Plano Premium")
        api.post(f"/api/orcamentos/{a['id']}/recusar", json={"motivo": "caro"})
        ativos = api.get("/api/orcamentos?aba=ativos").json()["data"]
        recusados = api.get("/api/orcamentos?aba=recusados").json()["data"]
        assert [o["id"] for o in ativos] == [b["id"]]
        assert [o["id"] for o in recusados] == [a["id"]]
        assert api.get("/api/orcamentos?aba=aceitos").json()["data"] == []
        assert [o["id"] for o in api.get("/api/orcamentos?q=premium").json()["data"]] == [b["id"]]
        assert len(api.get("/api/orcamentos?q=padaria").json()["data"]) == 2, "q matches empresa"
        assert len(api.get(f"/api/orcamentos?negocio_id={negocio['id']}").json()["data"]) == 2
        assert api.get("/api/orcamentos?status=recusado").json()["data"][0]["id"] == a["id"]

    def test_invalid_tab_is_422(self, api):
        assert api.get("/api/orcamentos?aba=todos").status_code == 422

    def test_past_validade_reads_as_expirado(self, api, catalogo, negocio, igig_db):
        orc = _criar(api, negocio, [_item_gestao(catalogo)],
                     validade=(hoje_local() - timedelta(days=1)).isoformat())
        assert api.get(f"/api/orcamentos/{orc['id']}").json()["data"]["status"] == "expirado"
        assert _linhas(igig_db, "orcamento", id=orc["id"])[0]["status"] == "expirado"
        assert [o["id"] for o in api.get("/api/orcamentos?aba=recusados").json()["data"]] == [orc["id"]]

    def test_null_validade_never_expires(self, api, catalogo, negocio):
        orc = _criar(api, negocio, [_item_gestao(catalogo)])
        assert orc["validade"] is None
        assert api.get(f"/api/orcamentos/{orc['id']}").json()["data"]["status"] == "rascunho"

    def test_patch_recomputes_and_voids_the_pdf(self, api, catalogo, negocio, igig_db):
        orc = _criar(api, negocio, [_item_gestao(catalogo)])
        api.post(f"/api/orcamentos/{orc['id']}/pdf")
        assert _linhas(igig_db, "orcamento", id=orc["id"])[0]["pdf_key"]
        resp = api.patch(f"/api/orcamentos/{orc['id']}",
                         json={"itens": [_item_post(catalogo, qtd=1)], "titulo": "Novo"})
        assert resp.status_code == 200, resp.text
        dados = resp.json()["data"]
        assert dados["titulo"] == "Novo"
        assert dados["total_mensal"] == 12 * 80
        assert dados["pdf_key"] is None, "a PDF must never show numbers the proposal no longer has"
        assert len(_linhas(igig_db, "orcamento_item", orcamento_id=orc["id"])) == 1

    def test_patch_discount_only_keeps_items(self, api, catalogo, negocio):
        orc = _criar(api, negocio, [_item_gestao(catalogo)])
        dados = api.patch(f"/api/orcamentos/{orc['id']}", json={"desconto": 50}).json()["data"]
        assert dados["total_mensal"] == 450.0
        assert len(dados["itens"]) == 1

    def test_empty_patch_is_422(self, api, catalogo, negocio):
        orc = _criar(api, negocio, [_item_gestao(catalogo)])
        assert api.patch(f"/api/orcamentos/{orc['id']}", json={}).status_code == 422

    def test_closed_orcamento_is_frozen(self, api, catalogo, negocio):
        orc = _criar(api, negocio, [_item_gestao(catalogo)])
        api.post(f"/api/orcamentos/{orc['id']}/recusar", json={"motivo": "caro"})
        resp = api.patch(f"/api/orcamentos/{orc['id']}", json={"titulo": "X"})
        assert resp.status_code == 409
        assert resp.json()["code"] == "orcamento_bloqueado"

    def test_nova_versao_clones_and_supersedes(self, api, catalogo, negocio, igig_db):
        orc = _criar(api, negocio, [_item_post(catalogo), _item_gestao(catalogo)], desconto=20)
        resp = api.post(f"/api/orcamentos/{orc['id']}/nova-versao")
        assert resp.status_code == 201, resp.text
        nova = resp.json()["data"]
        assert nova["versao"] == 2 and nova["status"] == "rascunho"
        assert nova["total_mensal"] == orc["total_mensal"]
        assert [i["descricao"] for i in nova["itens"]] == ["Post feed", "Gestão de DMs"]
        assert nova["itens"][0]["dias_semana"] == SEG | QUA | SEX
        assert _linhas(igig_db, "orcamento", id=orc["id"])[0]["status"] == "substituido"

    def test_nova_versao_does_not_inherit_a_past_validade(self, api, catalogo, negocio):
        orc = _criar(api, negocio, [_item_gestao(catalogo)],
                     validade=(hoje_local() - timedelta(days=3)).isoformat())
        nova = api.post(f"/api/orcamentos/{orc['id']}/nova-versao").json()["data"]
        assert nova["validade"] is None and nova["status"] == "rascunho"

    def test_recusar(self, api, catalogo, negocio):
        orc = _criar(api, negocio, [_item_gestao(catalogo)])
        resp = api.post(f"/api/orcamentos/{orc['id']}/recusar", json={"motivo": "Achou caro"})
        assert resp.status_code == 200
        dados = resp.json()["data"]
        assert dados["status"] == "recusado"
        assert dados["motivo_recusa"] == "Achou caro" and dados["recusado_em"]

    def test_recusar_needs_a_reason(self, api, catalogo, negocio):
        orc = _criar(api, negocio, [_item_gestao(catalogo)])
        resp = api.post(f"/api/orcamentos/{orc['id']}/recusar", json={"motivo": "  "})
        assert resp.status_code == 422
        assert resp.json()["code"] == "motivo_obrigatorio"


# ── Aceite ──────────────────────────────────────────────────────────
def _esperadas(dias: int, qtd: int, inicio: date) -> int:
    return sum(
        qtd for d in range(30) if dias & (1 << (inicio + timedelta(days=d)).weekday())
    )


class TestAceite:
    def test_runs_the_funnels_fechado_transition(self, api, catalogo, negocio, etapas, igig_db):
        orc = _criar(api, negocio, [_item_post(catalogo), _item_gestao(catalogo)])
        resp = api.post(f"/api/orcamentos/{orc['id']}/aceitar")
        assert resp.status_code == 200, resp.text
        dados = resp.json()["data"]
        assert dados["orcamento"]["status"] == "aceito" and dados["orcamento"]["aceito_em"]
        assert dados["negocio"]["status"] == "ganho"
        assert dados["negocio"]["etapa_id"] == etapas["fechado"]["id"]
        assert dados["negocio"]["orcamento_aceito_id"] == orc["id"]
        assert dados["cliente"]["nome"] == "Padaria Sol"
        assert dados["orcamento"]["cliente_id"] == dados["cliente"]["id"]
        # The move is in the history — it went through the seed's move_card.
        movimentos = _linhas(igig_db, "pipeline_movimentos", entidade_id=negocio["id"],
                             para_etapa_id=etapas["fechado"]["id"])
        assert len(movimentos) == 1

    def test_supersedes_the_open_siblings(self, api, catalogo, negocio, igig_db):
        a = _criar(api, negocio, [_item_gestao(catalogo)])
        b = _criar(api, negocio, [_item_gestao(catalogo)])
        api.post(f"/api/orcamentos/{b['id']}/aceitar")
        assert _linhas(igig_db, "orcamento", id=a["id"])[0]["status"] == "substituido"

    def test_generates_pautas_for_recurring_criacao_items_only(
        self, api, catalogo, negocio, igig_db
    ):
        orc = _criar(api, negocio, [
            _item_post(catalogo, dias=SEG | QUA | SEX, qtd=2),
            {**_item_gestao(catalogo)},
            {"produto_servico_id": catalogo["Reels"]["id"], "secao": "criacao_conteudo",
             "descricao": "Reels avulso", "preco_unitario": 250, "quantidade": 2},
        ])
        dados = api.post(f"/api/orcamentos/{orc['id']}/aceitar").json()["data"]
        esperadas = _esperadas(SEG | QUA | SEX, 2, hoje_local())
        assert dados["pautas_criadas"] == esperadas
        pautas = _linhas(igig_db, "pauta", cliente_id=dados["cliente"]["id"])
        assert len(pautas) == esperadas
        item_post = next(i for i in dados["orcamento"]["itens"] if i["descricao"] == "Post feed")
        assert {p["orcamento_item_id"] for p in pautas} == {item_post["id"]}
        assert all(p["gerada_automaticamente"] is True for p in pautas)
        assert all(p["formato"] == "feed" for p in pautas), "format comes from the catalogue"
        for p in pautas:
            dia = date.fromisoformat(p["data_publicacao"][:10])
            assert dia.weekday() in (0, 2, 4)
            assert hoje_local() <= dia < hoje_local() + timedelta(days=30)
        assert _linhas(igig_db, "tarefa") == [], "pautas only — esteira tarefas on demand"

    def test_reaccepting_is_idempotent(self, api, catalogo, negocio, igig_db):
        orc = _criar(api, negocio, [_item_post(catalogo)])
        primeiro = api.post(f"/api/orcamentos/{orc['id']}/aceitar").json()["data"]
        segundo = api.post(f"/api/orcamentos/{orc['id']}/aceitar")
        assert segundo.status_code == 200
        assert segundo.json()["data"]["pautas_criadas"] == 0
        assert len(_linhas(igig_db, "pauta")) == primeiro["pautas_criadas"]
        assert len(_linhas(igig_db, "cliente")) == 1

    def test_another_orcamento_after_the_deal_closed_is_409(self, api, catalogo, negocio):
        a = _criar(api, negocio, [_item_gestao(catalogo)])
        b = _criar(api, negocio, [_item_gestao(catalogo)])
        api.post(f"/api/orcamentos/{a['id']}/aceitar")
        resp = api.post(f"/api/orcamentos/{b['id']}/aceitar")
        assert resp.status_code == 409
        assert resp.json()["code"] == "negocio_ganho"

    def test_expired_is_409(self, api, catalogo, negocio):
        orc = _criar(api, negocio, [_item_gestao(catalogo)],
                     validade=(hoje_local() - timedelta(days=1)).isoformat())
        resp = api.post(f"/api/orcamentos/{orc['id']}/aceitar")
        assert resp.status_code == 409
        assert resp.json()["code"] == "orcamento_expirado"

    def test_refused_is_409(self, api, catalogo, negocio):
        orc = _criar(api, negocio, [_item_gestao(catalogo)])
        api.post(f"/api/orcamentos/{orc['id']}/recusar", json={"motivo": "caro"})
        resp = api.post(f"/api/orcamentos/{orc['id']}/aceitar")
        assert resp.status_code == 409
        assert resp.json()["code"] == "orcamento_invalido"

    def test_accepted_is_frozen(self, api, catalogo, negocio):
        orc = _criar(api, negocio, [_item_gestao(catalogo)])
        api.post(f"/api/orcamentos/{orc['id']}/aceitar")
        for resp in (
            api.patch(f"/api/orcamentos/{orc['id']}", json={"titulo": "X"}),
            api.post(f"/api/orcamentos/{orc['id']}/nova-versao"),
            api.post(f"/api/orcamentos/{orc['id']}/recusar", json={"motivo": "x"}),
        ):
            assert resp.status_code == 409
            assert resp.json()["code"] == "orcamento_bloqueado"

    def test_requires_auth(self, api, catalogo, negocio):
        orc = _criar(api, negocio, [_item_gestao(catalogo)])
        assert api.raw().post(f"/api/orcamentos/{orc['id']}/aceitar").status_code == 401


# ── PDF ─────────────────────────────────────────────────────────────
class TestPdf:
    def test_generates_a_real_pdf_in_the_private_bucket(
        self, api, catalogo, negocio, equipe, storage
    ):
        orc = _criar(api, negocio, [_item_post(catalogo), _item_gestao(catalogo)],
                     titulo="Social media mensal",
                     limites_escopo={"revisoes_incluidas": 3, "valor_excedente": 90})
        resp = api.post(f"/api/orcamentos/{orc['id']}/pdf")
        assert resp.status_code == 200, resp.text
        dados = resp.json()["data"]
        assert dados["pdf_key"] == f"{ORG}/orcamentos/{orc['id']}/v1.pdf"
        assert dados["url"].startswith(f"fake://storage/{BUCKET}/")
        texto = _pdf_texto(storage, dados["pdf_key"])
        for esperado in ("Agência Aurora", "Social media mensal", "João", "Padaria Sol",
                         "Seg, Qua, Sex × 2", "Gestão de DMs", "Total mensal", "R$ 2.420,00",
                         "R$ 90,00"):
            assert esperado in texto, f"{esperado!r} missing from the PDF"

    def test_never_carries_the_agencys_internal_cost(
        self, api, catalogo, negocio, equipe, storage
    ):
        orc = _criar(api, negocio, [_item_post(catalogo)])
        chave = api.post(f"/api/orcamentos/{orc['id']}/pdf").json()["data"]["pdf_key"]
        texto = _pdf_texto(storage, chave).lower()
        assert "custo" not in texto and "margem" not in texto
        assert "4.800" not in texto  # custo_estimado of 48h × R$100

    def test_get_returns_a_signed_url(self, api, catalogo, negocio):
        orc = _criar(api, negocio, [_item_gestao(catalogo)])
        api.post(f"/api/orcamentos/{orc['id']}/pdf")
        resp = api.get(f"/api/orcamentos/{orc['id']}/pdf")
        assert resp.status_code == 200
        assert "expires=" in resp.json()["data"]["url"]

    def test_get_before_generating_is_409(self, api, catalogo, negocio):
        orc = _criar(api, negocio, [_item_gestao(catalogo)])
        resp = api.get(f"/api/orcamentos/{orc['id']}/pdf")
        assert resp.status_code == 409
        assert resp.json()["code"] == "pdf_nao_gerado"

    def test_requires_auth(self, api, catalogo, negocio):
        orc = _criar(api, negocio, [_item_gestao(catalogo)])
        assert api.raw().post(f"/api/orcamentos/{orc['id']}/pdf").status_code == 401


# ── Contrato ────────────────────────────────────────────────────────
@pytest.fixture
def aceito(api, catalogo, negocio):
    orc = _criar(api, negocio, [_item_post(catalogo), _item_gestao(catalogo)],
                 limites_escopo={"revisoes_incluidas": 2, "valor_excedente": 90})
    return api.post(f"/api/orcamentos/{orc['id']}/aceitar").json()["data"]


class TestContrato:
    def test_only_an_accepted_orcamento_generates_a_contract(self, api, catalogo, negocio):
        orc = _criar(api, negocio, [_item_gestao(catalogo)])
        resp = api.post(f"/api/orcamentos/{orc['id']}/contrato",
                        json={"modalidade_assinatura": "fisica"})
        assert resp.status_code == 409
        assert resp.json()["code"] == "orcamento_nao_aceito"

    def test_fisica(self, api, aceito, storage):
        orc = aceito["orcamento"]
        resp = api.post(f"/api/orcamentos/{orc['id']}/contrato",
                        json={"modalidade_assinatura": "fisica", "dia_vencimento": 10, "vias": 3})
        assert resp.status_code == 201, resp.text
        dados = resp.json()["data"]
        contrato = dados["contrato"]
        assert contrato["valor_mensal"] == orc["total_mensal"]
        assert contrato["posts_por_mes"] == 24
        assert contrato["valor_excedente"] == 90.0
        assert contrato["modalidade_assinatura"] == "fisica"
        assert contrato["status"] == "aguardando_assinatura"
        assert contrato["cliente_id"] == aceito["cliente"]["id"]
        assert contrato["orcamento_id"] == orc["id"]
        assert dados["assinatura"] is None, "física never touches e-signature"
        texto = _pdf_texto(storage, contrato["documento_key"])
        assert "3 (três) vias" in texto
        assert "Testemunha 1" in texto and "CONTRATANTE" in texto
        assert "todo dia 10" in texto

    def test_digital_takes_the_signature_path(self, api, aceito, storage):
        orc = aceito["orcamento"]
        resp = api.post(f"/api/orcamentos/{orc['id']}/contrato",
                        json={"modalidade_assinatura": "digital"})
        assert resp.status_code == 201, resp.text
        dados = resp.json()["data"]
        assert dados["assinatura"]["dry_run"] is True
        assert dados["assinatura"]["external_id"].startswith(f"{ORG}.")
        assert dados["contrato"]["assinatura_external_id"] == dados["assinatura"]["external_id"]
        texto = _pdf_texto(storage, dados["contrato"]["documento_key"])
        assert "vias" not in texto and "assinatura eletrônica" in texto

    def test_one_live_contract_per_orcamento(self, api, aceito):
        orc = aceito["orcamento"]
        api.post(f"/api/orcamentos/{orc['id']}/contrato", json={"modalidade_assinatura": "fisica"})
        resp = api.post(f"/api/orcamentos/{orc['id']}/contrato",
                        json={"modalidade_assinatura": "fisica"})
        assert resp.status_code == 409
        assert resp.json()["code"] == "contrato_existente"

    def test_invalid_modalidade_is_422(self, api, aceito):
        resp = api.post(f"/api/orcamentos/{aceito['orcamento']['id']}/contrato",
                        json={"modalidade_assinatura": "fax"})
        assert resp.status_code == 422

    def test_list_by_cliente_and_pdf_url(self, api, aceito):
        orc = aceito["orcamento"]
        contrato = api.post(f"/api/orcamentos/{orc['id']}/contrato",
                            json={"modalidade_assinatura": "fisica"}).json()["data"]["contrato"]
        lista = api.get(f"/api/contratos?cliente_id={aceito['cliente']['id']}").json()["data"]
        assert [c["id"] for c in lista] == [contrato["id"]]
        assert api.get("/api/contratos?cliente_id=outro").json()["data"] == []
        url = api.get(f"/api/contratos/{contrato['id']}/pdf").json()["data"]
        assert url["url"].startswith("fake://") and url["url_assinado"] is None

    def test_requires_auth(self, api):
        assert api.raw().get("/api/contratos").status_code == 401


class TestMarcarAssinado:
    def _contrato(self, api, aceito, modalidade="fisica"):
        return api.post(f"/api/orcamentos/{aceito['orcamento']['id']}/contrato",
                        json={"modalidade_assinatura": modalidade}).json()["data"]["contrato"]

    def test_fisica_with_scan_activates_contract_and_client(self, api, aceito, igig_db):
        contrato = self._contrato(api, aceito)
        resp = api.post(f"/api/contratos/{contrato['id']}/marcar-assinado",
                        files={"arquivo": ("assinado.pdf", b"%PDF-1.4 scan", "application/pdf")})
        assert resp.status_code == 200, resp.text
        dados = resp.json()["data"]
        assert dados["status"] == "ativo"
        assert dados["assinado_manual_em"] and dados["assinado_em"]
        assert dados["documento_assinado_key"] == (
            f"{ORG}/contratos/{contrato['id']}/assinado-assinado.pdf"
        )
        assert _linhas(igig_db, "cliente", id=aceito["cliente"]["id"])[0]["status"] == "ativo"
        urls = api.get(f"/api/contratos/{contrato['id']}/pdf").json()["data"]
        assert urls["url_assinado"]

    def test_fisica_without_scan(self, api, aceito):
        contrato = self._contrato(api, aceito)
        resp = api.post(f"/api/contratos/{contrato['id']}/marcar-assinado")
        assert resp.status_code == 200
        assert resp.json()["data"].get("documento_assinado_key") is None

    def test_digital_cannot_be_marked_by_hand(self, api, aceito):
        contrato = self._contrato(api, aceito, "digital")
        resp = api.post(f"/api/contratos/{contrato['id']}/marcar-assinado")
        assert resp.status_code == 409
        assert resp.json()["code"] == "contrato_digital"

    def test_twice_is_409(self, api, aceito):
        contrato = self._contrato(api, aceito)
        api.post(f"/api/contratos/{contrato['id']}/marcar-assinado")
        resp = api.post(f"/api/contratos/{contrato['id']}/marcar-assinado")
        assert resp.status_code == 409
        assert resp.json()["code"] == "contrato_ja_assinado"

    def test_wrong_file_type_is_422(self, api, aceito):
        contrato = self._contrato(api, aceito)
        resp = api.post(f"/api/contratos/{contrato['id']}/marcar-assinado",
                        files={"arquivo": ("x.exe", b"MZ", "application/octet-stream")})
        assert resp.status_code == 422
        assert resp.json()["code"] == "arquivo_invalido"

    def test_unknown_contract_is_404(self, api):
        assert api.post("/api/contratos/nao-existe/marcar-assinado").status_code == 404

    def test_requires_auth(self, api):
        assert api.raw().post("/api/contratos/x/marcar-assinado").status_code == 401


# ── Legacy endpoints are gone ───────────────────────────────────────
@pytest.mark.parametrize("metodo, caminho", [
    ("post", "/api/comercial/estimar"),
    ("get", "/api/comercial/orcamentos"),
    ("post", "/api/comercial/orcamentos"),
    ("post", "/api/comercial/orcamentos/x/preco"),
    ("post", "/api/comercial/contratos/gerar"),
])
def test_legacy_orcamento_endpoints_are_removed(api, metodo, caminho):
    """Replaced by /api/orcamentos* and /api/orcamentos/{id}/contrato (wave 2)."""
    resp = getattr(api, metodo)(caminho, **({"json": {}} if metodo == "post" else {}))
    assert resp.status_code in (404, 405)
