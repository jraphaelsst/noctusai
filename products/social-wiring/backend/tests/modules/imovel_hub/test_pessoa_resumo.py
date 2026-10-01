"""`GET /api/clientes/{id}/resumo` — the person page payload (contract §4.5)."""
from __future__ import annotations

from uuid import uuid4

import pytest

from tests.modules.imovel_hub.conftest import ORG_ID, auth
from tests.modules.imovel_hub.relacionamentos_rows import (
    atendimento_row,
    cliente_row,
    espelho,
    interesse,
    juncao,
    proprietario,
    registro,
    seed_tabelas,
    touch_row,
)

TOP_KEYS = {"cliente", "papeis", "contatos", "atendimentos", "contagens"}
ATENDIMENTO_KEYS = {
    "id", "titulo", "etapa", "status", "arquivado", "titular", "lado", "papel",
    "parte_id", "imovel_pendente", "imoveis", "created_at",
}


def parte(atendimento_id, cliente_id, lado, papel="vendedor") -> dict:
    return {
        "id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": atendimento_id,
        "cliente_id": cliente_id, "empresa_id": None, "lado": lado, "papel": papel,
    }


@pytest.fixture
def base(client, scoped):
    seed_tabelas(
        scoped,
        imovel_registry=[registro("ONE1"), registro("ONE2")],
        imoveis=[espelho("ONE1"), espelho("ONE2")],
        imovel_dados=[],
        pipeline_stages=[{"id": "11111111-1111-4111-8111-111111111111", "org_id": ORG_ID,
                          "pipeline": "funil", "slug": "novo", "label": "Novo lead", "posicao": 0}],
        atendimentos=[], atendimento_partes=[], atendimento_imoveis=[], cliente_touches=[],
        cliente_imovel_interesses=[], imovel_proprietarios=[], roteiros=[],
    )
    return scoped


def get(client, cid):
    return client.get(f"/api/clientes/{cid}/resumo", headers=auth())


def test_unknown_cliente_404(client, base):
    resp = get(client, uuid4())
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "NOT_FOUND"


def test_titular_lead_shape_and_counts(client, base):
    ana = cliente_row()
    etapa = "11111111-1111-4111-8111-111111111111"
    at = atendimento_row(cliente_id=ana["id"], etapa_id=etapa, titulo="Ana — ONE1")
    seed_tabelas(
        base,
        clientes=[ana], atendimentos=[at],
        atendimento_imoveis=[juncao(at["id"], "ONE1", principal=True), juncao(at["id"], "ONE2")],
        cliente_touches=[touch_row(ana["id"])],
        cliente_imovel_interesses=[interesse(ana["id"], "ONE1"), interesse(ana["id"], "ONE2", deleted_at="2026-03-01T00:00:00+00:00")],
        roteiros=[{"id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": at["id"]}],
    )
    resp = get(client, ana["id"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == TOP_KEYS
    assert body["papeis"] == ["lead", "comprador"]
    assert body["contatos"] == {"celular": "+5511999990001", "email": "ana@example.com", "chave_canonica": "+5511999990001"}
    for chave in ("id", "nome", "nome_oficial", "cpf", "celular", "email", "estado_civil"):
        assert chave in body["cliente"]
    (a,) = body["atendimentos"]
    assert set(a) == ATENDIMENTO_KEYS
    assert a["titular"] is True and a["lado"] == "comprador" and a["parte_id"] is None
    assert a["etapa"] == {"id": etapa, "nome": "Novo lead"}
    assert a["imoveis"] == ["ONE1", "ONE2"] and a["imovel_pendente"] is False
    assert body["contagens"] == {"interesses": 1, "propriedades": 0, "roteiros": 1, "atendimentos": 1}


def test_vendedor_who_owns_is_vendedor_and_proprietario_only(client, base):
    vend = cliente_row(nome="Vera")
    titular = cliente_row(nome="Tito")
    at = atendimento_row(cliente_id=titular["id"])
    p = parte(at["id"], vend["id"], "vendedor")
    seed_tabelas(
        base,
        clientes=[vend, titular], atendimentos=[at], atendimento_partes=[p],
        imovel_proprietarios=[proprietario("ONE1", cliente_id=vend["id"])],
    )
    body = get(client, vend["id"]).json()
    assert body["papeis"] == ["vendedor", "proprietario"]
    (a,) = body["atendimentos"]
    assert a["titular"] is False and a["lado"] == "vendedor" and a["parte_id"] == p["id"]
    assert a["papel"] == "vendedor" and a["etapa"] is None
    assert a["imovel_pendente"] is True and a["imoveis"] == []  # derived, never stored
    assert body["contagens"]["propriedades"] == 1


def test_roles_overlap_both_ways(client, base):
    """A comprador who is also a vendedor on another deal carries BOTH roles —
    the one payload serves /clientes/:id and /vendedores/:id."""
    pessoa = cliente_row(nome="Duplo")
    outro = cliente_row(nome="Outro")
    propria = atendimento_row(cliente_id=pessoa["id"], created_at="2026-02-01T00:00:00+00:00")
    alheia = atendimento_row(cliente_id=outro["id"], created_at="2026-03-01T00:00:00+00:00")
    seed_tabelas(
        base, clientes=[pessoa, outro], atendimentos=[propria, alheia],
        atendimento_partes=[parte(alheia["id"], pessoa["id"], "vendedor")],
    )
    body = get(client, pessoa["id"]).json()
    assert body["papeis"] == ["lead", "comprador", "vendedor"]
    assert [a["id"] for a in body["atendimentos"]] == [alheia["id"], propria["id"]]  # newest first
    assert body["contagens"]["atendimentos"] == 2


def test_titular_row_wins_over_a_parte_row_for_the_same_atendimento(client, base):
    pessoa = cliente_row()
    at = atendimento_row(cliente_id=pessoa["id"])
    seed_tabelas(base, clientes=[pessoa], atendimentos=[at],
                 atendimento_partes=[parte(at["id"], pessoa["id"], "vendedor")])
    body = get(client, pessoa["id"]).json()
    assert len(body["atendimentos"]) == 1 and body["atendimentos"][0]["titular"] is True


def test_a_cliente_with_no_history_is_empty_not_an_error(client, base):
    solo = cliente_row()
    seed_tabelas(base, clientes=[solo])
    body = get(client, solo["id"]).json()
    assert body["papeis"] == [] and body["atendimentos"] == []
    assert body["contagens"] == {"interesses": 0, "propriedades": 0, "roteiros": 0, "atendimentos": 0}
