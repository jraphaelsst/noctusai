"""POST /propostas/{id}/aceitar and /pos-aceite through the REAL router into the
REAL `propostas.aceite` — the seam the CRUD tests stop at (their 503 case skips
once aceite.py exists) and the aceite tests start after (they call the function).

Only the response shape the FE consumes is asserted here (CONTRACT §4.2/§4.4):
bare body, `{proposta, contrato_id, geracao, pos_aceite, passos}`, the seed error
envelope on a refusal. Step semantics are owned by test_aceite_propostas.py.
"""
from __future__ import annotations

from tests.modules.card_hub.propostas_aceite.test_aceite_propostas import _seed

PASSOS = ["materializar", "visita", "contrato", "status", "funil", "pos_aceite"]


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


def _url(ids: dict, suffix: str) -> str:
    return f"/api/clientes/{ids['cliente']}/propostas/{ids['proposta']}{suffix}"


def test_aceitar_route_runs_the_real_orchestration(client, scoped):
    ids = _seed(scoped)
    resp = client.post(_url(ids, "/aceitar"), json={}, headers=_auth())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "data" not in body  # card_hub bodies are bare
    assert set(body) >= {"proposta", "contrato_id", "geracao", "pos_aceite", "passos"}
    assert body["proposta"]["status"] == "aceita"
    assert body["proposta"]["id"] == ids["proposta"]
    assert body["contrato_id"] and body["proposta"]["contrato_id"] == body["contrato_id"]
    assert [p["passo"] for p in body["passos"]] == PASSOS
    por_passo = {p["passo"]: p for p in body["passos"]}
    for passo in ("materializar", "visita", "contrato", "status"):
        assert por_passo[passo]["status"] == "ok", por_passo[passo]
    # funil / pos_aceite belong to other slices: whatever they report, it is a
    # recorded state, never a silent omission, and the accept stands.
    for passo in ("funil", "pos_aceite"):
        assert por_passo[passo]["status"] in {"ok", "erro", "pulado"}
    assert set(body["geracao"]) >= {"pronto", "faltando", "bloqueios", "avisos"}


def test_aceitar_refusal_uses_the_seed_error_envelope(client, scoped):
    ids = _seed(scoped, status="recusada")
    resp = client.post(_url(ids, "/aceitar"), json={}, headers=_auth())
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "proposta_fechada"


def test_pos_aceite_route_refuses_a_proposta_not_aceita(client, scoped):
    ids = _seed(scoped, status="enviada")
    resp = client.post(_url(ids, "/pos-aceite"), json={}, headers=_auth())
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "proposta_nao_aceita"


def test_retomar_route_has_the_aceitar_shape(client, scoped):
    ids = _seed(scoped)
    assert client.post(_url(ids, "/aceitar"), json={}, headers=_auth()).status_code == 200
    resp = client.post(_url(ids, "/pos-aceite"), json={}, headers=_auth())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) >= {"proposta", "contrato_id", "geracao", "pos_aceite", "passos"}
    assert "proposta_row" not in body  # the seam's internal row never leaks
    assert body["proposta"]["status"] == "aceita" and body["geracao"] is None
    assert [p["passo"] for p in body["passos"]] == ["funil", "pos_aceite"]


def test_aceitar_without_valor_is_400_valor_obrigatorio(client, scoped):
    ids = _seed(scoped)
    scoped.table("atendimento_propostas").update({"valor_proposto": None}).eq(
        "id", ids["proposta"]
    ).execute()
    resp = client.post(_url(ids, "/aceitar"), json={}, headers=_auth())
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "valor_obrigatorio"


def test_aceitar_unknown_proposta_is_404(client, scoped):
    ids = _seed(scoped)
    ids = {**ids, "proposta": "00000000-0000-0000-0000-000000000001"}
    resp = client.post(_url(ids, "/aceitar"), json={}, headers=_auth())
    assert resp.status_code == 404
