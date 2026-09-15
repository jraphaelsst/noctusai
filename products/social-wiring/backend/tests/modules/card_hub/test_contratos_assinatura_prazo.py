"""Contratos — `assinatura_data` + `prazo_pendencias_dias` (migration 114).

WHAT THESE PIN
--------------
- both fields round-trip through the existing `PATCH .../contratos/{id}` and
  come back on every contract read (PATCH response AND the list);
- `prazo_pendencias_dias = null` is a real state — "use the office default"
  (`contrato_gerador.politica.prazo_pendencias_dias`), never zero days;
- a zero / negative prazo and a malformed date are 400 VALIDATION_ERROR with a
  pt-BR message, not a driver-level 500 from the DB CHECK;
- a refused PATCH writes nothing.

Auth is not re-tested here — `test_auth_boundary.py` enumerates every mounted
card_hub route (the PATCH included) and asserts a strict 401 on each.
"""
from __future__ import annotations

from uuid import uuid4

from tests.modules.card_hub.conftest import ORG_ID, cliente_row

PDF = ("contrato.pdf", b"%PDF-1.7 fake", "application/pdf")


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


def _seed(scoped) -> str:
    cid, aid = str(uuid4()), str(uuid4())
    scoped.set_table_data("clientes", [cliente_row(cid, nome="Luciano")])
    scoped.set_table_data("atendimentos", [{
        "id": aid, "org_id": ORG_ID, "cliente_id": cid, "lead_id": None,
        "meta_ads_lead_id": None, "status": "aberta", "substituida_por": None,
        "arquivado": False, "titulo": "Compra do apto",
        "created_at": "2026-01-01T00:00:00+00:00", "closed_at": None,
    }])
    scoped.set_table_data("atendimento_contratos", [])
    scoped.set_table_data("atendimento_contrato_versoes", [])
    scoped.set_table_data("atendimento_contrato_versao_acessos", [])
    return cid


def _criar(client, cid) -> str:
    r = client.post(
        f"/api/clientes/{cid}/contratos",
        files={"file": PDF},
        data={"titulo": "Contrato de compra e venda"},
        headers=_auth(),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _patch(client, cid, contrato_id, **body):
    return client.patch(
        f"/api/clientes/{cid}/contratos/{contrato_id}", json=body, headers=_auth()
    )


def _mensagem_400(r) -> str:
    assert r.status_code == 400, r.text
    erro = r.json()["error"]
    assert erro["code"] == "VALIDATION_ERROR"
    return erro["message"]


class TestRoundTrip:
    def test_a_new_contract_has_neither_set(self, client, scoped, fake_storage):
        cid = _seed(scoped)
        _criar(client, cid)
        contrato = client.get(f"/api/clientes/{cid}/contratos", headers=_auth()).json()["contratos"][0]
        assert contrato["assinatura_data"] is None
        assert contrato["prazo_pendencias_dias"] is None

    def test_both_fields_round_trip_on_patch_and_list(self, client, scoped, fake_storage):
        cid = _seed(scoped)
        contrato_id = _criar(client, cid)
        r = _patch(client, cid, contrato_id, assinatura_data="2026-10-05", prazo_pendencias_dias=15)
        assert r.status_code == 200, r.text
        assert r.json()["assinatura_data"] == "2026-10-05"
        assert r.json()["prazo_pendencias_dias"] == 15

        listado = client.get(f"/api/clientes/{cid}/contratos", headers=_auth()).json()["contratos"][0]
        assert listado["assinatura_data"] == "2026-10-05"
        assert listado["prazo_pendencias_dias"] == 15

    def test_null_prazo_returns_to_the_office_default(self, client, scoped, fake_storage):
        cid = _seed(scoped)
        contrato_id = _criar(client, cid)
        _patch(client, cid, contrato_id, prazo_pendencias_dias=20)
        r = _patch(client, cid, contrato_id, prazo_pendencias_dias=None, assinatura_data=None)
        assert r.status_code == 200, r.text
        assert r.json()["prazo_pendencias_dias"] is None
        assert r.json()["assinatura_data"] is None

    def test_a_status_only_patch_leaves_both_alone(self, client, scoped, fake_storage):
        cid = _seed(scoped)
        contrato_id = _criar(client, cid)
        _patch(client, cid, contrato_id, assinatura_data="2026-10-05", prazo_pendencias_dias=7)
        r = _patch(client, cid, contrato_id, status="em_revisao")
        assert (r.json()["assinatura_data"], r.json()["prazo_pendencias_dias"]) == ("2026-10-05", 7)


class TestValidation:
    def test_zero_or_negative_prazo_is_refused(self, client, scoped, fake_storage):
        cid = _seed(scoped)
        contrato_id = _criar(client, cid)
        assert "maior que zero" in _mensagem_400(_patch(client, cid, contrato_id, prazo_pendencias_dias=0))
        assert "maior que zero" in _mensagem_400(_patch(client, cid, contrato_id, prazo_pendencias_dias=-3))

    def test_a_malformed_date_is_refused_by_name(self, client, scoped, fake_storage):
        cid = _seed(scoped)
        contrato_id = _criar(client, cid)
        assert "AAAA-MM-DD" in _mensagem_400(_patch(client, cid, contrato_id, assinatura_data="05/10/2026"))
        assert "AAAA-MM-DD" in _mensagem_400(_patch(client, cid, contrato_id, assinatura_data="2026-02-30"))

    def test_a_refused_patch_writes_nothing(self, client, scoped, fake_storage):
        cid = _seed(scoped)
        contrato_id = _criar(client, cid)
        _patch(client, cid, contrato_id, titulo="Novo título", prazo_pendencias_dias=0)
        contrato = client.get(f"/api/clientes/{cid}/contratos", headers=_auth()).json()["contratos"][0]
        assert contrato["titulo"] == "Contrato de compra e venda"
