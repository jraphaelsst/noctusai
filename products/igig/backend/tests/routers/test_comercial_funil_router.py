"""Comercial funnel — negócio cards on the seed pipeline (roadmap R2/R3/R4).

The rule that carries the weight: a deal cannot be CLOSED without naming the
orçamento the lead accepted (409 `orcamento_obrigatorio`). Closing accepts that
orçamento, supersedes its open siblings, marks the negócio ganho and creates
the Cliente from the lead — once, however many times it is retried or however
many of the lead's negócios close.
"""
from datetime import date, timedelta

import pytest
from noctusai_lib.testing.clients import TEST_USER_ID

from app.dependencies import coerce_org_uuid
from app.pipelines import COMERCIAL_PADRAO

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
        from app.pipelines import exigir_admin_da_org

        app.dependency_overrides[exigir_admin_da_org] = lambda: None
        try:
            resp = api.delete(f"/api/comercial/pipeline/stages/{etapas['fechado']['id']}")
            assert resp.status_code == 400
            renomeada = api.patch(
                f"/api/comercial/pipeline/stages/{etapas['fechado']['id']}",
                json={"label": "Contrato fechado"},
            )
            assert renomeada.status_code == 200, "renaming a system stage is allowed"
        finally:
            app.dependency_overrides.pop(exigir_admin_da_org, None)

    def test_non_admin_cannot_reorder(self, api, etapas):
        resp = api.post("/api/comercial/pipeline/stages/reordenar",
                        json={"ordem": [e["id"] for e in etapas.values()]})
        assert resp.status_code == 403


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

    def test_an_already_accepted_orcamento_closes_too(self, api, negocio, etapas, igig_db):
        aceito = _orcamento(igig_db, negocio, status="aceito")
        resp = _mover(api, negocio["id"], etapas["fechado"]["id"], orcamento_id=aceito["id"])
        assert resp.status_code == 200, resp.text

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
        ontem = (date.today() - timedelta(days=1)).isoformat()
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
