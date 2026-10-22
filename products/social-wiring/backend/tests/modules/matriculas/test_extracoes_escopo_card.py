"""`GET /api/matriculas/extracoes?cliente_id=` — the contract matrícula picker's
source is scoped, server-side, to the imóveis linked to the card.

A pick feeds the contract's IMÓVEL description, so another deal's matrícula
must not be returnable for this use. Auth is covered by
`test_matriculas_auth_boundary.py` (strict 401 on every mounted route).
"""
from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

from tests.modules.matriculas.conftest import ORG_ID, extracao_row

CLIENTE = str(uuid4())
PATH = "app.modules.matriculas.router.atendimento_imoveis_svc.codigos_do_cliente"


def _ids(resp):
    assert resp.status_code == 200, resp.text
    return {r["id"] for r in resp.json()["data"]}


def _seed(client):
    meu = extracao_row(str(uuid4()), codigo="AP1")
    outro = extracao_row(str(uuid4()), codigo="AP2")
    orfa = extracao_row(str(uuid4()), codigo=None)
    client.mock_supabase.set_table_data("matricula_extracoes", [meu, outro, orfa])
    return meu, outro, orfa


def test_only_the_cards_imoveis_matriculas_are_returned(client):
    meu, _outro, _orfa = _seed(client)
    with patch(PATH, return_value=["AP1"]):
        resp = client.get("/api/matriculas/extracoes", params={"cliente_id": CLIENTE})
    assert _ids(resp) == {meu["id"]}


def test_a_card_without_a_linked_imovel_gets_an_empty_list_not_the_org_pool(client):
    _seed(client)
    with patch(PATH, return_value=[]):
        resp = client.get("/api/matriculas/extracoes", params={"cliente_id": CLIENTE})
    assert _ids(resp) == set()


def test_a_malformed_cliente_id_is_a_422(client):
    resp = client.get("/api/matriculas/extracoes", params={"cliente_id": "nao-e-uuid"})
    assert resp.status_code == 422, resp.text


def test_real_resolution_from_atendimento_imoveis_no_patching(client):
    """The códigos come from `atendimento_imoveis` of THIS cliente's
    atendimentos only — another cliente's link and a soft-deleted link are
    not the card's imóveis."""
    meu, outro, orfa = _seed(client)
    at_meu, at_outro = str(uuid4()), str(uuid4())
    client.mock_supabase.set_table_data("atendimentos", [
        {"id": at_meu, "org_id": ORG_ID, "cliente_id": CLIENTE},
        {"id": at_outro, "org_id": ORG_ID, "cliente_id": str(uuid4())},
    ])
    client.mock_supabase.set_table_data("atendimento_imoveis", [
        {"id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": at_meu, "codigo": "AP1", "deleted_at": None},
        {"id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": at_outro, "codigo": "AP2", "deleted_at": None},
    ])
    resp = client.get("/api/matriculas/extracoes", params={"cliente_id": CLIENTE})
    assert _ids(resp) == {meu["id"]}
    assert outro["id"] not in _ids(resp) and orfa["id"] not in _ids(resp)
