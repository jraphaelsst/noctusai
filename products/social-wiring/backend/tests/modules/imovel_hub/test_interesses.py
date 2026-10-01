"""Interesses of a cliente (contract §4.1) — `cliente_imovel_interesses`."""
from __future__ import annotations

from uuid import uuid4

import pytest

from tests.modules.imovel_hub.conftest import auth
from tests.modules.imovel_hub.relacionamentos_rows import (
    cliente_row,
    espelho,
    interesse,
    registro,
    seed_tabelas,
)

ITEM_KEYS = {
    "id", "codigo", "origem", "created_at", "created_by", "imovel",
    "lead_id", "meta_ads_lead_id",
}


@pytest.fixture
def cenario(client, scoped):
    cliente = cliente_row()
    seed_tabelas(
        scoped,
        clientes=[cliente],
        imovel_registry=[registro("ONE1"), registro("ONE2"), registro("ONE3")],
        imoveis=[espelho("ONE1"), espelho("ONE2")],
        imovel_dados=[],
        cliente_imovel_interesses=[],
    )
    return {"cliente": cliente, "scoped": scoped}


def url(c, suffix=""):
    return f"/api/clientes/{c['cliente']['id']}/interesses{suffix}"


class TestList:
    def test_exact_keys_and_order_created_at_desc(self, client, cenario):
        cid = cenario["cliente"]["id"]
        cenario["scoped"].set_table_data(
            "cliente_imovel_interesses",
            [
                interesse(cid, "ONE1", origem="lead", created_at="2026-01-01T00:00:00+00:00"),
                interesse(cid, "ONE2", created_at="2026-03-01T00:00:00+00:00"),
                interesse(cid, "ONE3", deleted_at="2026-03-02T00:00:00+00:00"),
            ],
        )
        resp = client.get(url(cenario), headers=auth())
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body) == {"items", "total"}
        assert body["total"] == 2
        assert [i["codigo"] for i in body["items"]] == ["ONE2", "ONE1"]
        assert set(body["items"][0]) == ITEM_KEYS
        # the spec'd row fields ride on `imovel`
        for chave in ("codigo", "foto_destaque", "endereco", "complemento", "valor", "valor_tipo"):
            assert chave in body["items"][0]["imovel"]
        assert body["items"][0]["imovel"]["complemento"] == "apto 91"

    def test_unknown_cliente_is_404(self, client, cenario):
        assert client.get(f"/api/clientes/{uuid4()}/interesses", headers=auth()).status_code == 404

    def test_other_clientes_rows_are_not_returned(self, client, cenario):
        outro = cliente_row(nome="Outra")
        cenario["scoped"].set_table_data("clientes", [cenario["cliente"], outro])
        cenario["scoped"].set_table_data("cliente_imovel_interesses", [interesse(outro["id"], "ONE1")])
        assert client.get(url(cenario), headers=auth()).json()["items"] == []


class TestAdd:
    def test_manual_add_201(self, client, cenario):
        resp = client.post(url(cenario), json={"codigo": "one1"}, headers=auth())
        assert resp.status_code == 201, resp.text
        item = resp.json()
        assert set(item) == ITEM_KEYS
        assert item["codigo"] == "ONE1" and item["origem"] == "manual"
        assert item["imovel"]["codigo"] == "ONE1"

    def test_origem_permuta_and_campanha_accepted(self, client, cenario):
        assert client.post(url(cenario), json={"codigo": "ONE1", "origem": "permuta"}, headers=auth()).json()["origem"] == "permuta"
        assert client.post(url(cenario), json={"codigo": "ONE2", "origem": "campanha"}, headers=auth()).json()["origem"] == "campanha"

    @pytest.mark.parametrize("origem", ["lead", "roteiro", "x"])
    def test_system_origens_are_422(self, client, cenario, origem):
        resp = client.post(url(cenario), json={"codigo": "ONE1", "origem": origem}, headers=auth())
        assert resp.status_code == 422

    def test_duplicate_409(self, client, cenario):
        client.post(url(cenario), json={"codigo": "ONE1"}, headers=auth())
        resp = client.post(url(cenario), json={"codigo": "ONE1"}, headers=auth())
        assert resp.status_code == 409
        assert resp.json()["error"]["message"] == "Este imóvel já está na lista de interesses."

    def test_unknown_imovel_404_copy(self, client, cenario):
        resp = client.post(url(cenario), json={"codigo": "ZZ9"}, headers=auth())
        assert resp.status_code == 404
        assert resp.json()["error"]["message"] == (
            "Imóvel ZZ9 não encontrado. Selecione um imóvel do catálogo ou cadastre-o."
        )

    def test_soft_deleted_is_revived_keeping_its_id(self, client, cenario):
        cid = cenario["cliente"]["id"]
        morto = interesse(cid, "ONE1", origem="lead", deleted_at="2026-03-01T00:00:00+00:00")
        cenario["scoped"].set_table_data("cliente_imovel_interesses", [morto])
        resp = client.post(url(cenario), json={"codigo": "ONE1"}, headers=auth())
        assert resp.status_code == 201
        rows = cenario["scoped"].table("cliente_imovel_interesses").select("*").execute().data
        assert len(rows) == 1 and rows[0]["id"] == morto["id"]
        assert rows[0]["deleted_at"] is None and rows[0]["origem"] == "manual"


class TestDelete:
    def test_soft_delete_204_and_not_listed(self, client, cenario):
        cid = cenario["cliente"]["id"]
        vivo = interesse(cid, "ONE1")
        cenario["scoped"].set_table_data("cliente_imovel_interesses", [vivo])
        assert client.delete(url(cenario, f"/{vivo['id']}"), headers=auth()).status_code == 204
        row = cenario["scoped"].table("cliente_imovel_interesses").select("*").execute().data[0]
        assert row["deleted_at"] is not None
        assert client.get(url(cenario), headers=auth()).json()["total"] == 0

    def test_someone_elses_row_is_404(self, client, cenario):
        alheio = interesse(uuid4(), "ONE1")
        cenario["scoped"].set_table_data("cliente_imovel_interesses", [alheio])
        assert client.delete(url(cenario, f"/{alheio['id']}"), headers=auth()).status_code == 404

    def test_removing_never_touches_junction_rows(self, client, cenario):
        from tests.modules.imovel_hub.relacionamentos_rows import juncao

        cid = cenario["cliente"]["id"]
        vivo = interesse(cid, "ONE1")
        j = juncao(uuid4(), "ONE1")
        cenario["scoped"].set_table_data("cliente_imovel_interesses", [vivo])
        cenario["scoped"].set_table_data("atendimento_imoveis", [j])
        client.delete(url(cenario, f"/{vivo['id']}"), headers=auth())
        assert cenario["scoped"].table("atendimento_imoveis").select("*").execute().data[0]["deleted_at"] is None
