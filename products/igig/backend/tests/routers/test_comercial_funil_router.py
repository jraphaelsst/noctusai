"""Comercial funnel — negócio cards on the seed pipeline (roadmap R2/R3/R4).

The rule that carries the weight: a deal cannot be CLOSED without naming the
orçamento the lead accepted (409 `orcamento_obrigatorio`). Closing accepts that
orçamento, supersedes its open siblings, marks the negócio ganho and creates
the Cliente from the lead — once, however many times it is retried or however
many of the lead's negócios close.
"""
from datetime import timedelta

import pytest
from noctusai_lib.testing.clients import TEST_USER_ID

from app.dependencies import coerce_org_uuid
from app.pipelines import COMERCIAL_PADRAO
from app.services import comercial_funil
from app.services.orcamentos import hoje_local

ORG = str(coerce_org_uuid("test-org-123"))


@pytest.fixture
def api(crm_api):
    return crm_api


@pytest.fixture
def etapas(api) -> dict[str, dict]:
    resp = api.get("/api/comercial/pipeline/stages")
    assert resp.status_code == 200, resp.text
    return {s["slug"]: s for s in resp.json()["data"]}


@pytest.fixture
def negocio(api, etapas) -> dict:
    resp = api.post("/api/comercial/negocios", json={
        "lead": {"nome": "João", "empresa": "Padaria Sol", "email": "joao@sol.com"},
        "valor_estimado": 3000,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def _orcamento(igig_db, negocio, *, status="enviado", versao=1, validade=None, **extra):
    return igig_db.table("orcamento").insert({
        "org_id": ORG, "negocio_id": negocio["id"], "lead_id": negocio["lead_id"],
        "titulo": f"Proposta v{versao}", "versao": versao, "status": status,
        "validade": validade, **extra,
    }).execute().data[0]


def _mover(api, negocio_id, etapa_id, **extra):
    return api.post(
        f"/api/comercial/negocios/{negocio_id}/mover-etapa",
        json={"para_etapa_id": etapa_id, **extra},
    )


def _linha(igig_db, tabela, registro_id):
    return next(r for r in igig_db.table(tabela)._data if r["id"] == registro_id)


# ── Stages ──────────────────────────────────────────────────────────
class TestEtapas:
    def test_requires_auth(self, api):
        assert api.raw().get("/api/comercial/pipeline/stages").status_code == 401

    def test_defaults_are_the_owners_funnel(self, etapas):
        assert [e["label"] for e in etapas.values()] == [
            "Leads", "Qualificação", "Negociação", "Agendar briefing", "Fechado",
        ]
        assert etapas["fechado"]["papel"] == "fechado"
        assert [s.slug for s in COMERCIAL_PADRAO] == list(etapas)

    def test_the_fechado_stage_cannot_be_deleted(self, api, etapas):
        from app.main import app
        from app.pipelines import exigir_admin_do_quadro

        app.dependency_overrides[exigir_admin_do_quadro] = lambda: None
        try:
            resp = api.delete(f"/api/comercial/pipeline/stages/{etapas['fechado']['id']}")
            assert resp.status_code == 400
            renomeada = api.patch(
                f"/api/comercial/pipeline/stages/{etapas['fechado']['id']}",
                json={"label": "Contrato fechado"},
            )
            assert renomeada.status_code == 200, "renaming a system stage is allowed"
        finally:
            app.dependency_overrides.pop(exigir_admin_do_quadro, None)

    def test_non_admin_cannot_reorder(self, api, etapas):
        resp = api.post("/api/comercial/pipeline/stages/reordenar",
                        json={"ordem": [e["id"] for e in etapas.values()]})
        assert resp.status_code == 403


# ── Stage role (achado comercial #14) ─────────────────────────────────
class TestPapelEtapa:
    @pytest.fixture
    def admin(self, api):
        from app.main import app
        from app.pipelines import exigir_admin_do_quadro

        app.dependency_overrides[exigir_admin_do_quadro] = lambda: None
        yield api
        app.dependency_overrides.pop(exigir_admin_do_quadro, None)

    def test_requires_auth(self, api, etapas):
        resp = api.raw().patch(
            f"/api/comercial/pipeline/stages/{etapas['negociacao']['id']}/papel",
            json={"papel": "fechado"},
        )
        assert resp.status_code == 401

    def test_non_admin_is_refused(self, api, etapas):
        resp = api.patch(
            f"/api/comercial/pipeline/stages/{etapas['negociacao']['id']}/papel",
            json={"papel": "fechado"},
        )
        assert resp.status_code == 403

    def test_reassigning_to_a_new_stage_clears_the_old_holder(self, admin, etapas):
        resp = admin.patch(
            f"/api/comercial/pipeline/stages/{etapas['negociacao']['id']}/papel",
            json={"papel": "fechado"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["papel"] == "fechado"

        etapas_atuais = {e["slug"]: e for e in admin.get("/api/comercial/pipeline/stages").json()["data"]}
        assert etapas_atuais["fechado"]["papel"] is None

    def test_refuses_to_clear_the_sole_fechado_holder(self, admin, etapas):
        resp = admin.patch(
            f"/api/comercial/pipeline/stages/{etapas['fechado']['id']}/papel",
            json={"papel": None},
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "papel_fechado_obrigatorio"

    def test_no_op_when_already_holding_the_role(self, admin, etapas):
        resp = admin.patch(
            f"/api/comercial/pipeline/stages/{etapas['fechado']['id']}/papel",
            json={"papel": "fechado"},
        )
        assert resp.status_code == 200, resp.text

    def test_unknown_stage_returns_404(self, admin):
        resp = admin.patch(
            "/api/comercial/pipeline/stages/nao-existe/papel", json={"papel": "fechado"}
        )
        assert resp.status_code == 404


# ── Create / edit ───────────────────────────────────────────────────
class TestCriarNegocio:
    def test_requires_auth(self, api):
        resp = api.raw().post("/api/comercial/negocios", json={"lead": {"nome": "X"}})
        assert resp.status_code == 401

    def test_manual_lead_lands_in_the_entry_stage(self, negocio, etapas, igig_db):
        assert negocio["etapa_id"] == etapas["leads"]["id"]
        assert negocio["status"] == "aberto"
        assert negocio["titulo"] == "Padaria Sol"
        lead = _linha(igig_db, "lead", negocio["lead_id"])
        assert lead["origem"] == "manual"

    def test_entry_is_recorded_in_the_history(self, negocio, igig_db):
        historico = [m for m in igig_db.table("pipeline_movimentos")._data
                     if m["entidade_id"] == negocio["id"]]
        assert len(historico) == 1 and historico[0]["de_etapa_id"] is None
        assert historico[0]["responsavel_id"] == TEST_USER_ID

    def test_existing_lead(self, api, etapas, igig_db):
        lead = igig_db.table("lead").insert(
            {"org_id": ORG, "nome": "Maria", "origem": "whatsapp"}
        ).execute().data[0]
        resp = api.post("/api/comercial/negocios", json={"lead_id": lead["id"]})
        assert resp.status_code == 201
        assert resp.json()["data"]["lead_id"] == lead["id"]

    def test_newest_card_goes_on_top(self, api, negocio, etapas):
        segundo = api.post("/api/comercial/negocios", json={"lead": {"nome": "Ana"}}).json()["data"]
        coluna = api.get("/api/comercial/board").json()["data"][0]
        assert [c["id"] for c in coluna["cards"]] == [segundo["id"], negocio["id"]]

    @pytest.mark.parametrize("corpo", [{}, {"lead_id": "x", "lead": {"nome": "Y"}}])
    def test_exactly_one_lead_source(self, api, etapas, corpo):
        assert api.post("/api/comercial/negocios", json=corpo).status_code == 422

    def test_unknown_lead_returns_404(self, api, etapas):
        assert api.post("/api/comercial/negocios", json={"lead_id": "nao-existe"}).status_code == 404

    def test_patch_edits_value_and_title(self, api, negocio):
        resp = api.patch(f"/api/comercial/negocios/{negocio['id']}",
                         json={"titulo": "Retainer Sol", "valor_estimado": 4500})
        assert resp.status_code == 200
        assert resp.json()["data"]["titulo"] == "Retainer Sol"

    def test_patch_requires_auth(self, api, negocio):
        resp = api.raw().patch(f"/api/comercial/negocios/{negocio['id']}", json={"titulo": "X"})
        assert resp.status_code == 401


# ── Board ───────────────────────────────────────────────────────────
class TestBoard:
    def test_requires_auth(self, api):
        assert api.raw().get("/api/comercial/board").status_code == 401

    def test_columns_and_lead_on_the_card(self, api, negocio):
        colunas = api.get("/api/comercial/board").json()["data"]
        assert [c["stage"]["slug"] for c in colunas] == [s.slug for s in COMERCIAL_PADRAO]
        card = colunas[0]["cards"][0]
        assert card["lead"]["nome"] == "João"
        assert colunas[0]["valorTotal"] == 3000


# ── Moves + closing ─────────────────────────────────────────────────
class TestMoverEtapa:
    def test_requires_auth(self, api, negocio, etapas):
        resp = api.raw().post(f"/api/comercial/negocios/{negocio['id']}/mover-etapa",
                              json={"para_etapa_id": etapas["qualificacao"]["id"]})
        assert resp.status_code == 401

    def test_free_movement_between_open_stages(self, api, negocio, etapas, igig_db):
        resp = _mover(api, negocio["id"], etapas["negociacao"]["id"])
        assert resp.status_code == 200, resp.text
        linha = _linha(igig_db, "negocio", negocio["id"])
        assert linha["etapa_id"] == etapas["negociacao"]["id"]
        assert linha["stage_entered_at"] != negocio["stage_entered_at"]

    def test_closing_without_an_orcamento_is_409(self, api, negocio, etapas, igig_db):
        resp = _mover(api, negocio["id"], etapas["fechado"]["id"])
        assert resp.status_code == 409
        assert resp.json()["code"] == "orcamento_obrigatorio"
        assert _linha(igig_db, "negocio", negocio["id"])["etapa_id"] == etapas["leads"]["id"]
        assert igig_db.table("cliente")._data == [], "nothing may be written on refusal"

    def test_closing_accepts_the_orcamento_and_creates_the_cliente(
        self, api, negocio, etapas, igig_db
    ):
        v1 = _orcamento(igig_db, negocio, versao=1)
        v2 = _orcamento(igig_db, negocio, versao=2)
        recusado = _orcamento(igig_db, negocio, versao=3, status="recusado")

        resp = _mover(api, negocio["id"], etapas["fechado"]["id"], orcamento_id=v2["id"])
        assert resp.status_code == 200, resp.text
        card = resp.json()["data"]
        assert card["status"] == "ganho"
        assert card["orcamento_aceito_id"] == v2["id"]

        assert _linha(igig_db, "orcamento", v2["id"])["status"] == "aceito"
        assert _linha(igig_db, "orcamento", v2["id"])["aceito_em"]
        assert _linha(igig_db, "orcamento", v1["id"])["status"] == "substituido"
        assert _linha(igig_db, "orcamento", recusado["id"])["status"] == "recusado"

        [cliente] = igig_db.table("cliente")._data
        assert cliente["nome"] == "Padaria Sol"
        assert cliente["lead_id"] == negocio["lead_id"]
        assert cliente["negocio_id"] == negocio["id"]
        assert card["cliente_id"] == cliente["id"]
        lead = _linha(igig_db, "lead", negocio["lead_id"])
        assert lead["status"] == "convertido" and lead["cliente_id"] == cliente["id"]

    def test_closing_via_drag_generates_pautas(self, api, negocio, etapas, igig_db):
        """Achado 2 / comercial achado 1: drag-to-Fechado used to close the
        deal WITHOUT ever generating a pauta — only the orçamento modal's ✓
        did. `_fechar` now calls the same shared `pautas.gerar` the modal's
        `/aceitar` calls, so both doors fill the calendar."""
        orc = _orcamento(igig_db, negocio)
        igig_db.table("orcamento_item").insert({
            "org_id": ORG, "orcamento_id": orc["id"], "produto_servico_id": None,
            "secao": "criacao_conteudo", "descricao": "Post feed", "preco_unitario": 80,
            "recorrente": True, "dias_semana": 1 | 4 | 16, "qtd_por_dia": 1,
            "quantidade_mensal": 12, "subtotal": 960, "ordem": 0,
        }).execute()

        resp = _mover(api, negocio["id"], etapas["fechado"]["id"], orcamento_id=orc["id"])
        assert resp.status_code == 200, resp.text
        cliente_id = resp.json()["data"]["cliente_id"]
        pautas_geradas = [p for p in igig_db.table("pauta")._data if p["cliente_id"] == cliente_id]
        assert len(pautas_geradas) > 0
        assert all(p["gerada_automaticamente"] is True for p in pautas_geradas)

    def test_an_already_accepted_orcamento_closes_too(self, api, negocio, etapas, igig_db):
        aceito = _orcamento(igig_db, negocio, status="aceito")
        resp = _mover(api, negocio["id"], etapas["fechado"]["id"], orcamento_id=aceito["id"])
        assert resp.status_code == 200, resp.text

    def test_abrir_negocio_with_cliente_id_reuses_it_on_close(self, api, etapas, igig_db):
        """Comercial achado 12 (upsell): a negócio opened FOR an existing
        cliente (`comercial_funil.abrir_negocio(cliente_id=...)`) must reuse
        that cliente on close — never `_garantir_cliente` spinning up a
        second one from the lead."""
        cliente = igig_db.table("cliente").insert(
            {"org_id": ORG, "nome": "Padaria Sol", "status": "ativo"}
        ).execute().data[0]
        lead = igig_db.table("lead").insert(
            {"org_id": ORG, "nome": "Novo contato", "empresa": "Padaria Sol"}
        ).execute().data[0]
        upsell = comercial_funil.abrir_negocio(
            igig_db, ORG, lead_id=lead["id"], titulo="Upsell — pacote maior",
            cliente_id=cliente["id"],
        )
        assert upsell["cliente_id"] == cliente["id"]
        orc = _orcamento(igig_db, upsell)
        resp = _mover(api, upsell["id"], etapas["fechado"]["id"], orcamento_id=orc["id"])
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["cliente_id"] == cliente["id"]
        assert len(igig_db.table("cliente")._data) == 1

    def test_criar_negocio_route_accepts_cliente_id_for_upsell(self, api, etapas, igig_db):
        """The ROUTE itself must carry `cliente_id` through, not just the
        service (achado comercial nota 1 — upsell): the FE "Novo
        negócio"/"Cliente existente" flows call `POST /negocios`, never
        `comercial_funil.abrir_negocio` directly."""
        cliente = igig_db.table("cliente").insert(
            {"org_id": ORG, "nome": "Padaria Sol", "status": "ativo"}
        ).execute().data[0]
        resp = api.post("/api/comercial/negocios", json={
            "lead": {"nome": "Padaria Sol", "email": "contato@sol.com"},
            "cliente_id": cliente["id"],
            "titulo": "Upsell — pacote maior",
        })
        assert resp.status_code == 201, resp.text
        negocio = resp.json()["data"]
        assert negocio["cliente_id"] == cliente["id"]

        orc = _orcamento(igig_db, negocio)
        fechado = _mover(api, negocio["id"], etapas["fechado"]["id"], orcamento_id=orc["id"])
        assert fechado.status_code == 200, fechado.text
        assert fechado.json()["data"]["cliente_id"] == cliente["id"]
        assert len(igig_db.table("cliente")._data) == 1

    def test_the_cliente_is_created_once_per_lead(self, api, negocio, etapas, igig_db):
        primeiro = _orcamento(igig_db, negocio)
        _mover(api, negocio["id"], etapas["fechado"]["id"], orcamento_id=primeiro["id"])
        outro = api.post("/api/comercial/negocios",
                         json={"lead_id": negocio["lead_id"], "titulo": "Upsell"}).json()["data"]
        orc = _orcamento(igig_db, outro)
        resp = _mover(api, outro["id"], etapas["fechado"]["id"], orcamento_id=orc["id"])
        assert resp.status_code == 200, resp.text
        assert len(igig_db.table("cliente")._data) == 1
        assert resp.json()["data"]["cliente_id"] == igig_db.table("cliente")._data[0]["id"]

    def test_another_negocios_orcamento_is_409(self, api, negocio, etapas, igig_db):
        outro = api.post("/api/comercial/negocios", json={"lead": {"nome": "Ana"}}).json()["data"]
        alheio = _orcamento(igig_db, outro)
        resp = _mover(api, negocio["id"], etapas["fechado"]["id"], orcamento_id=alheio["id"])
        assert resp.status_code == 409
        assert resp.json()["code"] == "orcamento_invalido"

    @pytest.mark.parametrize("status", ["recusado", "expirado", "substituido"])
    def test_a_closed_orcamento_cannot_be_accepted(self, api, negocio, etapas, igig_db, status):
        orc = _orcamento(igig_db, negocio, status=status)
        resp = _mover(api, negocio["id"], etapas["fechado"]["id"], orcamento_id=orc["id"])
        assert resp.status_code == 409
        assert resp.json()["code"] == "orcamento_invalido"

    def test_a_past_validity_is_409(self, api, negocio, etapas, igig_db):
        # The service's clock is America/Sao_Paulo (`orcamentos.hoje_local`); a
        # UTC `date.today()` is a day ahead from 21:00 BRT and made this flaky.
        ontem = (hoje_local() - timedelta(days=1)).isoformat()
        orc = _orcamento(igig_db, negocio, validade=ontem)
        resp = _mover(api, negocio["id"], etapas["fechado"]["id"], orcamento_id=orc["id"])
        assert resp.status_code == 409
        assert resp.json()["code"] == "orcamento_expirado"

    def test_no_validity_never_expires(self, api, negocio, etapas, igig_db):
        orc = _orcamento(igig_db, negocio, validade=None)
        resp = _mover(api, negocio["id"], etapas["fechado"]["id"], orcamento_id=orc["id"])
        assert resp.status_code == 200

    def test_a_sibling_already_accepted_is_409(self, api, negocio, etapas, igig_db):
        _orcamento(igig_db, negocio, versao=1, status="aceito")
        v2 = _orcamento(igig_db, negocio, versao=2)
        resp = _mover(api, negocio["id"], etapas["fechado"]["id"], orcamento_id=v2["id"])
        assert resp.status_code == 409
        assert resp.json()["code"] == "orcamento_ja_aceito"

    def test_a_won_deal_cannot_leave_fechado(self, api, negocio, etapas, igig_db):
        orc = _orcamento(igig_db, negocio)
        _mover(api, negocio["id"], etapas["fechado"]["id"], orcamento_id=orc["id"])
        resp = _mover(api, negocio["id"], etapas["negociacao"]["id"])
        assert resp.status_code == 409
        assert resp.json()["code"] == "negocio_ganho"

    def test_the_rule_follows_the_role_not_the_label(self, api, negocio, etapas, igig_db):
        """Renaming 'Fechado' must not open a bypass."""
        igig_db.table("pipeline_stages").update({"label": "Contrato"}).eq(
            "id", etapas["fechado"]["id"]).execute()
        resp = _mover(api, negocio["id"], etapas["fechado"]["id"])
        assert resp.json()["code"] == "orcamento_obrigatorio"

    def test_unknown_stage_returns_404(self, api, negocio):
        assert _mover(api, negocio["id"], "nao-existe").status_code == 404

    def test_unknown_negocio_returns_404(self, api, etapas):
        assert _mover(api, "nao-existe", etapas["qualificacao"]["id"]).status_code == 404


# ── Read (any status) ───────────────────────────────────────────────
class TestObterNegocio:
    def test_requires_auth(self, api, negocio):
        resp = api.raw().get(f"/api/comercial/negocios/{negocio['id']}")
        assert resp.status_code == 401

    def test_returns_the_same_card_shape_as_the_board(self, api, negocio):
        card = api.get(f"/api/comercial/negocios/{negocio['id']}").json()["data"]
        assert card["id"] == negocio["id"]
        assert card["lead"]["nome"] == "João"
        assert card["responsavel"] is None
        assert card["perdido_stage"] is None
        assert card["dwell_dias"] is None

    def test_a_perdido_negocio_opens_too(self, api, negocio, etapas):
        """Unlike the board (`GET /board`, open+ganho only), the deep-link
        lookup must open a lost deal — the archive links to it."""
        api.post(f"/api/comercial/negocios/{negocio['id']}/perder", json={"motivo": "achou caro"})
        card = api.get(f"/api/comercial/negocios/{negocio['id']}").json()["data"]
        assert card["status"] == "perdido"
        assert card["motivo_perda"] == "achou caro"
        assert card["perdido_stage"] == {"id": etapas["leads"]["id"], "label": "Leads"}
        assert card["dwell_dias"] is not None

    def test_a_ganho_negocio_opens_too(self, api, negocio, etapas, igig_db):
        orc = _orcamento(igig_db, negocio)
        _mover(api, negocio["id"], etapas["fechado"]["id"], orcamento_id=orc["id"])
        card = api.get(f"/api/comercial/negocios/{negocio['id']}").json()["data"]
        assert card["status"] == "ganho"

    def test_unknown_negocio_is_404(self, api):
        assert api.get("/api/comercial/negocios/nao-existe").status_code == 404

    def test_another_orgs_negocio_is_404(self, api, negocio, igig_db):
        igig_db.table("negocio").update({"org_id": "outra-org"}).eq("id", negocio["id"]).execute()
        assert api.get(f"/api/comercial/negocios/{negocio['id']}").status_code == 404


class TestListarNegocios:
    def test_requires_auth(self, api):
        assert api.raw().get("/api/comercial/negocios").status_code == 401

    def test_lists_every_status_unlike_the_board(self, api, negocio, etapas):
        api.post(f"/api/comercial/negocios/{negocio['id']}/perder", json={"motivo": "sumiu"})
        outro = api.post("/api/comercial/negocios", json={"lead": {"nome": "Ana"}}).json()["data"]
        ids = {c["id"] for c in api.get("/api/comercial/negocios").json()["data"]}
        assert ids == {negocio["id"], outro["id"]}

    def test_filters_by_status(self, api, negocio, etapas):
        api.post(f"/api/comercial/negocios/{negocio['id']}/perder", json={"motivo": "sumiu"})
        outro = api.post("/api/comercial/negocios", json={"lead": {"nome": "Ana"}}).json()["data"]
        perdidos = api.get("/api/comercial/negocios?status=perdido").json()["data"]
        assert [c["id"] for c in perdidos] == [negocio["id"]]
        abertos = api.get("/api/comercial/negocios?status=aberto").json()["data"]
        assert [c["id"] for c in abertos] == [outro["id"]]

    def test_q_searches_the_title(self, api, negocio):
        api.post("/api/comercial/negocios", json={"lead": {"nome": "Ana", "empresa": "Estúdio X"}})
        achados = api.get("/api/comercial/negocios?q=Sol").json()["data"]
        assert [c["id"] for c in achados] == [negocio["id"]]

    def test_org_scoped(self, api, negocio, igig_db):
        igig_db.table("negocio").insert({
            "org_id": "outra-org", "lead_id": negocio["lead_id"], "titulo": "De outra org",
            "etapa_id": negocio["etapa_id"], "status": "aberto", "kanban_pos": "1",
        }).execute()
        ids = {c["id"] for c in api.get("/api/comercial/negocios").json()["data"]}
        assert ids == {negocio["id"]}


# ── Lost ────────────────────────────────────────────────────────────
class TestPerder:
    def test_requires_auth(self, api, negocio):
        resp = api.raw().post(f"/api/comercial/negocios/{negocio['id']}/perder",
                              json={"motivo": "preço"})
        assert resp.status_code == 401

    def test_archives_with_reason_and_stage(self, api, negocio, etapas, igig_db):
        resp = api.post(f"/api/comercial/negocios/{negocio['id']}/perder",
                        json={"motivo": "achou caro"})
        assert resp.status_code == 200, resp.text
        linha = _linha(igig_db, "negocio", negocio["id"])
        assert linha["status"] == "perdido"
        assert linha["motivo_perda"] == "achou caro"
        assert linha["perdido_stage_id"] == etapas["leads"]["id"]
        assert linha["perdido_em"]
        board = api.get("/api/comercial/board").json()["data"]
        assert sum(c["total"] for c in board) == 0, "a lost deal leaves the funnel"

    def test_reason_is_required(self, api, negocio):
        resp = api.post(f"/api/comercial/negocios/{negocio['id']}/perder", json={"motivo": ""})
        assert resp.status_code == 422

    def test_a_lost_deal_cannot_be_lost_again_or_moved(self, api, negocio, etapas):
        api.post(f"/api/comercial/negocios/{negocio['id']}/perder", json={"motivo": "sumiu"})
        again = api.post(f"/api/comercial/negocios/{negocio['id']}/perder", json={"motivo": "x"})
        assert again.status_code == 409
        assert again.json()["code"] == "negocio_encerrado"
        movido = _mover(api, negocio["id"], etapas["qualificacao"]["id"])
        assert movido.status_code == 409
        assert movido.json()["code"] == "negocio_perdido"
