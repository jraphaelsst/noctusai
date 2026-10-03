"""`GET /api/imoveis/conflitos/pendentes` — the org-wide imóvel half of
Settings › Pendências (synthetic data only).

WHAT THESE PIN
--------------
- the route reaches the imovel_hub handler, NOT `imoveis_router`'s
  `GET /{codigo}` (a one-segment `/conflitos` would have been read as an
  imóvel code — the reason the path has two segments);
- it lists pending conflicts of EVERY imóvel in the org, each with its
  `codigo`, and never a decided one;
- strict `== 401` without a token (never `in (401, 404)`).
"""
from __future__ import annotations

from uuid import UUID, uuid4

from app.modules.imovel_hub import campos_extraidos_service as campos_svc
from tests.modules.imovel_hub.conftest import (
    CODIGO,
    ORG_ID,
    auth,
    dados_row,
    imovel_row,
    registry_row,
    seed,
)

ORG = UUID(ORG_ID)
OUTRO = "CA9876"
URL = "/api/imoveis/conflitos/pendentes"


def _abrir(scoped, codigo: str, lido: str) -> dict:
    return campos_svc.aplicar(
        scoped, ORG, codigo, "numero_registro_imoveis", lido,
        origem="matricula", documento_id=str(uuid4()),
    ).conflito


def _seed_dois(scoped) -> tuple[dict, dict]:
    seed(scoped, registry=[registry_row(), registry_row(OUTRO)],
         imoveis=[imovel_row(), imovel_row(OUTRO)], dados=[
        dados_row(numero_registro_imoveis="2º RI", numero_registro_imoveis_origem="manual"),
        dados_row(OUTRO, numero_registro_imoveis="3º RI", numero_registro_imoveis_origem="manual"),
    ])
    return _abrir(scoped, CODIGO, "1º RI"), _abrir(scoped, OUTRO, "4º RI")


def test_lists_every_pending_conflict_in_the_org_with_its_codigo(client, scoped):
    a, b = _seed_dois(scoped)
    resp = client.get(URL, headers=auth())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {i["id"] for i in body["items"]} == {a["id"], b["id"]}
    assert {i["codigo"] for i in body["items"]} == {CODIGO, OUTRO}
    assert body["total"] == 2


def test_a_decided_conflict_leaves_the_queue(client, scoped):
    a, b = _seed_dois(scoped)
    campos_svc.resolver(scoped, ORG, CODIGO, UUID(a["id"]), aceitar=False, decidido_por=None)
    body = client.get(URL, headers=auth()).json()
    assert [i["id"] for i in body["items"]] == [b["id"]]


def test_unauthenticated_is_strictly_401(anon_client):
    assert anon_client.get(URL).status_code == 401
