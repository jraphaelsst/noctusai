"""Atendimento imóveis (contract `atendimento-partes-imoveis` §3) — the
junction `atendimento_imoveis`: list / add / remove / principal, the
negociação invariant, the ingest linker and the sweep reconcile.

Contract-shape tests assert the EXACT wire field names (§3.1) — a rename is a
contract bug the FE would discover at runtime.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from tests.modules.imovel_hub.conftest import ORG_ID, auth
from tests.modules.imovel_hub.relacionamentos_rows import (
    atendimento_row,
    cliente_row,
    espelho,
    juncao,
    lead_row,
    meta_row,
    registro,
    seed_tabelas,
)

IMOVEL_KEYS = {
    "codigo", "titulo", "empreendimento", "logradouro", "numero", "complemento",
    "bairro", "cidade", "uf", "cep", "foto_destaque", "corretores", "captacao",
    "ativo_no_vista", "origem", "registrado", "fonte",
    # §0.1 additive
    "categoria", "valor_venda", "valor_locacao", "dormitorios", "suites", "vagas",
    "area_total", "area_privativa", "area_construida", "endereco", "valor", "valor_tipo",
}
ITEM_KEYS = {
    "id", "codigo", "origem", "principal", "em_negociacao", "created_at",
    "created_by", "imovel",
}


@pytest.fixture
def cenario(client, scoped):
    cliente = cliente_row()
    atendimento = atendimento_row(cliente_id=cliente["id"])
    seed_tabelas(
        scoped,
        clientes=[cliente],
        atendimentos=[atendimento],
        imovel_registry=[registro("ONE1"), registro("ONE2"), registro("ONE3")],
        imoveis=[espelho("ONE1"), espelho("ONE2")],
        imovel_dados=[],
        atendimento_imoveis=[],
        atendimento_negociacao=[],
        cliente_imovel_interesses=[],
    )
    return {"cliente": cliente, "atendimento": atendimento, "scoped": scoped}


def url(c, suffix=""):
    return f"/api/clientes/{c['cliente']['id']}/atendimento-imoveis{suffix}"


class TestListContract:
    def test_empty_atendimento_is_imovel_pendente(self, client, cenario):
        resp = client.get(url(cenario), headers=auth())
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body) == {"items", "total", "atendimento_id", "imovel_pendente"}
        assert body == {
            "items": [],
            "total": 0,
            "atendimento_id": cenario["atendimento"]["id"],
            "imovel_pendente": True,
        }

    def test_item_and_imovel_resumo_exact_keys(self, client, cenario):
        at = cenario["atendimento"]["id"]
        cenario["scoped"].set_table_data(
            "atendimento_imoveis", [juncao(at, "ONE1", principal=True)]
        )
        body = client.get(url(cenario), headers=auth()).json()
        assert body["imovel_pendente"] is False
        item = body["items"][0]
        assert set(item) == ITEM_KEYS
        assert set(item["imovel"]) == IMOVEL_KEYS
        assert item["imovel"]["endereco"] == "Rua das Palmeiras, 320 — Pinheiros, São Paulo/SP"
        assert item["imovel"]["valor"] == 850000.0
        assert item["imovel"]["valor_tipo"] == "venda"

    def test_principal_first_and_deleted_rows_are_hidden(self, client, cenario):
        at = cenario["atendimento"]["id"]
        cenario["scoped"].set_table_data(
            "atendimento_imoveis",
            [
                juncao(at, "ONE2", created_at="2026-01-01T00:00:00+00:00"),
                juncao(at, "ONE1", principal=True, created_at="2026-03-01T00:00:00+00:00"),
                juncao(at, "ONE3", deleted_at="2026-03-02T00:00:00+00:00"),
            ],
        )
        body = client.get(url(cenario), headers=auth()).json()
        assert [i["codigo"] for i in body["items"]] == ["ONE1", "ONE2"]
        assert body["total"] == 2

    def test_em_negociacao_flag(self, client, cenario):
        at = cenario["atendimento"]["id"]
        cenario["scoped"].set_table_data(
            "atendimento_imoveis", [juncao(at, "ONE1", principal=True), juncao(at, "ONE2")]
        )
        cenario["scoped"].set_table_data(
            "atendimento_negociacao", [{"org_id": ORG_ID, "atendimento_id": at, "imovel_codigo": "ONE2"}]
        )
        items = {i["codigo"]: i for i in client.get(url(cenario), headers=auth()).json()["items"]}
        assert items["ONE2"]["em_negociacao"] is True
        assert items["ONE1"]["em_negociacao"] is False

    def test_ambiguous_read_is_empty_never_409(self, client, cenario):
        cenario["scoped"].set_table_data(
            "atendimentos",
            [
                cenario["atendimento"],
                atendimento_row(cliente_id=cenario["cliente"]["id"]),
            ],
        )
        resp = client.get(url(cenario), headers=auth())
        assert resp.status_code == 200
        assert resp.json() == {
            "items": [], "total": 0, "atendimento_id": None, "imovel_pendente": False,
        }

    def test_unknown_cliente_is_404(self, client, cenario):
        resp = client.get(f"/api/clientes/{uuid4()}/atendimento-imoveis", headers=auth())
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"


class TestAdd:
    def test_first_imovel_becomes_principal_regardless(self, client, cenario):
        resp = client.post(url(cenario), json={"codigo": "one1"}, headers=auth())
        assert resp.status_code == 201, resp.text
        item = resp.json()
        assert set(item) == ITEM_KEYS
        assert item["codigo"] == "ONE1"  # canonicalised
        assert item["principal"] is True
        assert item["origem"] == "manual"
        rows = cenario["scoped"].table("atendimento_imoveis").select("*").execute().data
        assert len(rows) == 1 and rows[0]["atendimento_id"] == cenario["atendimento"]["id"]

    def test_principal_true_demotes_the_previous_principal(self, client, cenario):
        client.post(url(cenario), json={"codigo": "ONE1"}, headers=auth())
        resp = client.post(url(cenario), json={"codigo": "ONE2", "principal": True}, headers=auth())
        assert resp.status_code == 201
        rows = {r["codigo"]: r for r in cenario["scoped"].table("atendimento_imoveis").select("*").execute().data}
        assert rows["ONE2"]["principal"] is True
        assert rows["ONE1"]["principal"] is False
        assert sum(1 for r in rows.values() if r["principal"]) == 1

    def test_second_add_is_not_principal_by_default(self, client, cenario):
        client.post(url(cenario), json={"codigo": "ONE1"}, headers=auth())
        resp = client.post(url(cenario), json={"codigo": "ONE2"}, headers=auth())
        assert resp.json()["principal"] is False

    def test_duplicate_is_409_conflict_with_contract_copy(self, client, cenario):
        client.post(url(cenario), json={"codigo": "ONE1"}, headers=auth())
        resp = client.post(url(cenario), json={"codigo": "ONE1"}, headers=auth())
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CONFLICT"
        assert resp.json()["error"]["message"] == "Este imóvel já está vinculado ao atendimento."

    def test_unknown_codigo_is_404_with_contract_copy(self, client, cenario):
        resp = client.post(url(cenario), json={"codigo": "NOPE9"}, headers=auth())
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"
        assert resp.json()["error"]["message"] == (
            "Imóvel NOPE9 não encontrado. Selecione um imóvel do catálogo ou cadastre-o."
        )

    @pytest.mark.parametrize("origem", ["lead", "negociacao", "outra"])
    def test_system_origens_are_422(self, client, cenario, origem):
        resp = client.post(url(cenario), json={"codigo": "ONE1", "origem": origem}, headers=auth())
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_unknown_body_field_is_422(self, client, cenario):
        resp = client.post(url(cenario), json={"codigo": "ONE1", "extra": 1}, headers=auth())
        assert resp.status_code == 422

    def test_ambiguous_atendimento_is_409_with_candidates(self, client, cenario):
        outro = atendimento_row(cliente_id=cenario["cliente"]["id"])
        cenario["scoped"].set_table_data("atendimentos", [cenario["atendimento"], outro])
        resp = client.post(url(cenario), json={"codigo": "ONE1"}, headers=auth())
        assert resp.status_code == 409
        err = resp.json()["error"]
        assert err["code"] == "AMBIGUOUS_ATENDIMENTO"
        assert set(err["details"]["atendimentos"]) == {cenario["atendimento"]["id"], outro["id"]}

    def test_explicit_atendimento_id_resolves_the_ambiguity(self, client, cenario):
        outro = atendimento_row(cliente_id=cenario["cliente"]["id"])
        cenario["scoped"].set_table_data("atendimentos", [cenario["atendimento"], outro])
        resp = client.post(
            url(cenario),
            json={"codigo": "ONE1", "atendimento_id": outro["id"]},
            headers=auth(),
        )
        assert resp.status_code == 201
        row = cenario["scoped"].table("atendimento_imoveis").select("*").execute().data[0]
        assert row["atendimento_id"] == outro["id"]

    def test_soft_deleted_link_is_revived_not_duplicated(self, client, cenario):
        at = cenario["atendimento"]["id"]
        morto = juncao(at, "ONE1", deleted_at="2026-03-01T00:00:00+00:00", origem="lead")
        cenario["scoped"].set_table_data("atendimento_imoveis", [morto])
        resp = client.post(url(cenario), json={"codigo": "ONE1", "origem": "campanha"}, headers=auth())
        assert resp.status_code == 201
        rows = cenario["scoped"].table("atendimento_imoveis").select("*").execute().data
        assert len(rows) == 1
        assert rows[0]["id"] == morto["id"]
        assert rows[0]["deleted_at"] is None
        assert rows[0]["origem"] == "campanha"
        assert rows[0]["principal"] is True  # the only live one


class TestPrincipalAndRemove:
    def _dois(self, cenario):
        at = cenario["atendimento"]["id"]
        a = juncao(at, "ONE1", principal=True, created_at="2026-01-01T00:00:00+00:00")
        b = juncao(at, "ONE2", created_at="2026-01-02T00:00:00+00:00")
        cenario["scoped"].set_table_data("atendimento_imoveis", [a, b])
        return a, b

    def test_put_principal_demotes_previous_and_is_idempotent(self, client, cenario):
        a, b = self._dois(cenario)
        r1 = client.put(url(cenario, f"/{b['id']}/principal"), headers=auth())
        assert r1.status_code == 200, r1.text
        assert r1.json()["principal"] is True and set(r1.json()) == ITEM_KEYS
        r2 = client.put(url(cenario, f"/{b['id']}/principal"), headers=auth())
        assert r2.status_code == 200
        rows = {r["codigo"]: r["principal"] for r in cenario["scoped"].table("atendimento_imoveis").select("*").execute().data}
        assert rows == {"ONE1": False, "ONE2": True}

    def test_put_principal_of_someone_elses_row_is_404(self, client, cenario):
        estranho = juncao(uuid4(), "ONE1")
        cenario["scoped"].set_table_data("atendimento_imoveis", [estranho])
        resp = client.put(url(cenario, f"/{estranho['id']}/principal"), headers=auth())
        assert resp.status_code == 404

    def test_delete_is_soft_204_and_promotes_oldest_remaining(self, client, cenario):
        a, b = self._dois(cenario)
        resp = client.delete(url(cenario, f"/{a['id']}"), headers=auth())
        assert resp.status_code == 204
        rows = {r["codigo"]: r for r in cenario["scoped"].table("atendimento_imoveis").select("*").execute().data}
        assert rows["ONE1"]["deleted_at"] is not None
        assert rows["ONE1"]["principal"] is False
        assert rows["ONE2"]["principal"] is True

    def test_delete_the_imovel_em_negociacao_is_409(self, client, cenario):
        a, b = self._dois(cenario)
        cenario["scoped"].set_table_data(
            "atendimento_negociacao",
            [{"org_id": ORG_ID, "atendimento_id": a["atendimento_id"], "imovel_codigo": "ONE1"}],
        )
        resp = client.delete(url(cenario, f"/{a['id']}"), headers=auth())
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "IMOVEL_EM_NEGOCIACAO"
        assert resp.json()["error"]["message"] == (
            "Este imóvel está em negociação neste atendimento — altere a negociação antes de removê-lo."
        )

    def test_delete_the_last_imovel_is_409(self, client, cenario):
        at = cenario["atendimento"]["id"]
        unico = juncao(at, "ONE1", principal=True)
        cenario["scoped"].set_table_data("atendimento_imoveis", [unico])
        resp = client.delete(url(cenario, f"/{unico['id']}"), headers=auth())
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "ULTIMO_IMOVEL"
        assert resp.json()["error"]["message"] == "O atendimento precisa de pelo menos um imóvel."

    def test_delete_unknown_is_404(self, client, cenario):
        resp = client.delete(url(cenario, f"/{uuid4()}"), headers=auth())
        assert resp.status_code == 404


class TestNegociacaoInvariant:
    """§3.5 — `atendimento_negociacao.imovel_codigo` ∈ junction, through the
    REAL `negociacao_service` writer (no patching)."""

    def _atualizar(self, cenario, codigo):
        from app.modules.card_hub import negociacao_service as neg

        return neg.atualizar(
            cenario["scoped"],
            UUID(ORG_ID),
            UUID(cenario["cliente"]["id"]),
            valores={"imovel_codigo": codigo},
            usuario_id=None,
        )

    def test_setting_the_negotiated_imovel_links_it_as_negociacao_principal(self, client, cenario):
        self._atualizar(cenario, "one2")
        rows = cenario["scoped"].table("atendimento_imoveis").select("*").execute().data
        assert [(r["codigo"], r["origem"], r["principal"]) for r in rows] == [("ONE2", "negociacao", True)]

    def test_an_existing_lead_link_is_upgraded_and_made_principal(self, client, cenario):
        at = cenario["atendimento"]["id"]
        cenario["scoped"].set_table_data(
            "atendimento_imoveis",
            [juncao(at, "ONE1", principal=True, origem="lead"), juncao(at, "ONE2", origem="lead")],
        )
        self._atualizar(cenario, "ONE2")
        rows = {r["codigo"]: r for r in cenario["scoped"].table("atendimento_imoveis").select("*").execute().data}
        assert len(rows) == 2  # no duplicate row
        assert rows["ONE2"]["origem"] == "negociacao" and rows["ONE2"]["principal"] is True
        assert rows["ONE1"]["principal"] is False and rows["ONE1"]["origem"] == "lead"

    def test_a_soft_deleted_link_is_revived(self, client, cenario):
        at = cenario["atendimento"]["id"]
        morto = juncao(at, "ONE1", deleted_at="2026-03-01T00:00:00+00:00", origem="manual")
        cenario["scoped"].set_table_data("atendimento_imoveis", [morto])
        self._atualizar(cenario, "ONE1")
        rows = cenario["scoped"].table("atendimento_imoveis").select("*").execute().data
        assert len(rows) == 1 and rows[0]["id"] == morto["id"]
        assert rows[0]["deleted_at"] is None and rows[0]["origem"] == "negociacao"

    def test_clearing_the_codigo_does_not_unlink(self, client, cenario):
        self._atualizar(cenario, "ONE1")
        self._atualizar(cenario, None)
        rows = cenario["scoped"].table("atendimento_imoveis").select("*").execute().data
        assert len(rows) == 1 and rows[0]["deleted_at"] is None

    def test_unrelated_negociacao_patch_touches_no_junction(self, client, cenario):
        from app.modules.card_hub import negociacao_service as neg

        neg.atualizar(
            cenario["scoped"], UUID(ORG_ID), UUID(cenario["cliente"]["id"]),
            valores={"observacoes": "x"}, usuario_id=None,
        )
        assert cenario["scoped"].table("atendimento_imoveis").select("*").execute().data == []


class TestVincularLead:
    """§3.5 `vincular_lead` — Meta (REF) and manual leads link the imóvel AND the
    cliente interesse."""

    def _svc(self):
        from app.modules.imovel_hub import atendimento_imoveis_service as svc

        return svc

    def test_meta_lead_links_junction_and_interesse(self, client, cenario):
        scoped = cenario["scoped"]
        cliente = cenario["cliente"]
        meta = meta_row(codigo="ONE9441")
        lead = lead_row(codigo="ONE9441", meta_lead_id=meta["id"])
        at_meta = atendimento_row(cliente_id=cliente["id"], meta_ads_lead_id=meta["id"])
        at_lead = atendimento_row(cliente_id=cliente["id"], lead_id=lead["id"], substituida_por=at_meta["id"])
        seed_tabelas(
            scoped,
            leads=[lead],
            meta_ads_leads=[meta],
            atendimentos=[at_meta, at_lead],
            imovel_registry=[],  # ONE9441 was never registered: vincular_lead registers it
        )
        out = self._svc().vincular_lead(scoped, UUID(ORG_ID), meta_ads_lead_id=meta["id"])
        assert out["codigo"] == "ONE9441"
        assert set(out["atendimentos"]) == {at_meta["id"], at_lead["id"]}
        assert out["interesse"] is True

        registry = scoped.table("imovel_registry").select("*").execute().data
        assert [r["codigo_canonical"] for r in registry] == ["ONE9441"]
        assert registry[0]["origem_descoberta"] == "lead"
        junction = scoped.table("atendimento_imoveis").select("*").execute().data
        assert {r["atendimento_id"] for r in junction} == {at_meta["id"], at_lead["id"]}
        assert all(r["codigo"] == "ONE9441" and r["origem"] == "lead" and r["principal"] for r in junction)
        interesses = scoped.table("cliente_imovel_interesses").select("*").execute().data
        assert len(interesses) == 1
        assert interesses[0]["cliente_id"] == cliente["id"]
        assert interesses[0]["origem"] == "lead"
        assert interesses[0]["meta_ads_lead_id"] == meta["id"] and interesses[0]["lead_id"] is None

    def test_is_idempotent(self, client, cenario):
        scoped = cenario["scoped"]
        lead = lead_row(codigo="ONE1")
        at = atendimento_row(cliente_id=cenario["cliente"]["id"], lead_id=lead["id"])
        seed_tabelas(scoped, leads=[lead], atendimentos=[at])
        svc = self._svc()
        svc.vincular_lead(scoped, UUID(ORG_ID), lead_id=lead["id"])
        second = svc.vincular_lead(scoped, UUID(ORG_ID), lead_id=lead["id"])
        assert second["interesse"] is False
        assert len(scoped.table("atendimento_imoveis").select("*").execute().data) == 1
        assert len(scoped.table("cliente_imovel_interesses").select("*").execute().data) == 1

    def test_without_cliente_the_interesse_is_deferred_not_failed(self, client, cenario):
        scoped = cenario["scoped"]
        lead = lead_row(codigo="ONE1")
        at = atendimento_row(cliente_id=None, lead_id=lead["id"])
        seed_tabelas(scoped, leads=[lead], atendimentos=[at])
        out = self._svc().vincular_lead(scoped, UUID(ORG_ID), lead_id=lead["id"])
        assert out["interesse"] is None
        assert len(scoped.table("atendimento_imoveis").select("*").execute().data) == 1
        assert scoped.table("cliente_imovel_interesses").select("*").execute().data == []

    def test_lead_without_codigo_is_accepted_and_stays_pendente(self, client, cenario):
        scoped = cenario["scoped"]
        lead = lead_row(codigo=None)
        at = atendimento_row(cliente_id=cenario["cliente"]["id"], lead_id=lead["id"])
        seed_tabelas(scoped, leads=[lead], atendimentos=[at])
        out = self._svc().vincular_lead(scoped, UUID(ORG_ID), lead_id=lead["id"])
        assert out == {"codigo": None, "atendimentos": [], "interesse": None}
        body = client.get(
            f"/api/clientes/{cenario['cliente']['id']}/atendimento-imoveis", headers=auth()
        ).json()
        assert body["imovel_pendente"] is True

    def test_meta_lead_with_only_answers_ref_still_links(self, client, cenario):
        scoped = cenario["scoped"]
        meta = meta_row(codigo=None, answers={"REF": "one7777"})
        at = atendimento_row(cliente_id=cenario["cliente"]["id"], meta_ads_lead_id=meta["id"])
        seed_tabelas(scoped, leads=[], meta_ads_leads=[meta], atendimentos=[at], imovel_registry=[])
        out = self._svc().vincular_lead(scoped, UUID(ORG_ID), meta_ads_lead_id=meta["id"])
        assert out["codigo"] == "ONE7777"

    def test_a_removed_link_is_not_resurrected(self, client, cenario):
        scoped = cenario["scoped"]
        lead = lead_row(codigo="ONE1")
        at = atendimento_row(cliente_id=cenario["cliente"]["id"], lead_id=lead["id"])
        seed_tabelas(
            scoped, leads=[lead], atendimentos=[at],
            atendimento_imoveis=[juncao(at["id"], "ONE1", deleted_at="2026-03-01T00:00:00+00:00")],
        )
        self._svc().vincular_lead(scoped, UUID(ORG_ID), lead_id=lead["id"])
        rows = scoped.table("atendimento_imoveis").select("*").execute().data
        assert len(rows) == 1 and rows[0]["deleted_at"] is not None


class TestReconcile:
    """The clientes-sweep leg: a late cliente attach / a collapse / a failed
    ingest-time call all converge."""

    def _run(self, scoped):
        from app.modules.imovel_hub import atendimento_imoveis_service as svc

        return svc.reconcile(scoped, UUID(ORG_ID))

    def test_late_cliente_attach_lands_the_interesse(self, client, cenario):
        scoped = cenario["scoped"]
        lead = lead_row(codigo="ONE1")
        at = atendimento_row(cliente_id=None, lead_id=lead["id"])
        seed_tabelas(scoped, leads=[lead], atendimentos=[at])
        first = self._run(scoped)
        assert first["vinculos_criados"] == 1 and first["interesses_criados"] == 0
        # the sweep attaches the cliente …
        scoped.table("atendimentos").update({"cliente_id": cenario["cliente"]["id"]}).eq("id", at["id"]).execute()
        second = self._run(scoped)
        assert second["vinculos_criados"] == 0 and second["interesses_criados"] == 1
        third = self._run(scoped)
        assert third["vinculos_criados"] == 0 and third["interesses_criados"] == 0

    def test_collapsed_loser_links_land_on_the_survivor(self, client, cenario):
        scoped = cenario["scoped"]
        c = cenario["cliente"]["id"]
        lead_a = lead_row(codigo="ONE1")
        lead_b = lead_row(codigo="ONE2", created_at="2026-03-01T00:00:00+00:00")
        survivor = atendimento_row(cliente_id=c, lead_id=lead_a["id"], created_at="2026-02-01T00:00:00+00:00")
        loser = atendimento_row(
            cliente_id=c, lead_id=lead_b["id"], substituida_por=survivor["id"],
            created_at="2026-03-01T00:00:00+00:00",
        )
        seed_tabelas(scoped, leads=[lead_a, lead_b], atendimentos=[survivor, loser])
        self._run(scoped)
        rows = scoped.table("atendimento_imoveis").select("*").execute().data
        assert {(r["atendimento_id"], r["codigo"]) for r in rows} == {
            (survivor["id"], "ONE1"), (survivor["id"], "ONE2"),
        }
        assert [r["codigo"] for r in rows if r["principal"]] == ["ONE1"]
        assert {r["codigo"] for r in scoped.table("cliente_imovel_interesses").select("*").execute().data} == {"ONE1", "ONE2"}

    def test_never_resurrects_a_removed_interesse_or_link(self, client, cenario):
        scoped = cenario["scoped"]
        c = cenario["cliente"]["id"]
        lead = lead_row(codigo="ONE1")
        at = atendimento_row(cliente_id=c, lead_id=lead["id"])
        from tests.modules.imovel_hub.relacionamentos_rows import interesse

        seed_tabelas(
            scoped, leads=[lead], atendimentos=[at],
            atendimento_imoveis=[juncao(at["id"], "ONE1", deleted_at="2026-03-01T00:00:00+00:00")],
            cliente_imovel_interesses=[interesse(c, "ONE1", deleted_at="2026-03-01T00:00:00+00:00")],
        )
        out = self._run(scoped)
        assert out["vinculos_criados"] == 0 and out["interesses_criados"] == 0

    def test_registers_unknown_codigos(self, client, cenario):
        scoped = cenario["scoped"]
        lead = lead_row(codigo="NEW42")
        at = atendimento_row(cliente_id=cenario["cliente"]["id"], lead_id=lead["id"])
        seed_tabelas(scoped, leads=[lead], atendimentos=[at], imovel_registry=[])
        out = self._run(scoped)
        assert out["imoveis_registrados"] == 1
        assert [r["codigo_canonical"] for r in scoped.table("imovel_registry").select("*").execute().data] == ["NEW42"]

    def test_run_backfill_hook_runs_the_reconcile(self, client, cenario):
        """The hook in `clientes_service.run_backfill` (not just the service)."""
        from app.services import clientes_service

        scoped = cenario["scoped"]
        lead = lead_row(codigo="ONE1")
        at = atendimento_row(cliente_id=cenario["cliente"]["id"], lead_id=lead["id"])
        seed_tabelas(scoped, leads=[lead], atendimentos=[at], meta_ads_leads=[], cliente_touches=[])
        report = clientes_service.run_backfill(scoped, UUID(ORG_ID))
        assert report.imoveis_reconcile_falhou is False
        assert report.imoveis_vinculados == 1
        assert report.as_dict()["imoveis_vinculados"] == 1
