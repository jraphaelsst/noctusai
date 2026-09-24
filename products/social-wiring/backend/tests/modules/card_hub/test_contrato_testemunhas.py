"""`/api/clientes/{cliente_id}/contratos/{contrato_id}/testemunhas` —
per-contract witness selection (migration 168).

WHAT THESE PIN
--------------
- a fresh contract has no selection (`GET` -> `{"items": [], "total": 0}`);
- `PUT` REPLACES the whole selection, in the order sent, resolving each row
  against the CURRENT registry (nome/e-mail there wins);
- a duplicate `testemunha_id` in the same PUT is refused with a NAMED 400,
  never a silent de-dupe;
- a `testemunha_id` outside this org (or that does not exist) is a 404;
- a `testemunha_id` with no CPF ("CPF pendente") is refused with a NAMED
  400 — selection-time enforcement, defense in depth over the FE's own
  disabled-option gate;
- `PUT` with `[]` clears the selection.

Auth is NOT re-tested here — `test_auth_boundary_contrato_testemunhas.py`
asserts a strict 401 on both routes.
"""
from __future__ import annotations

from uuid import uuid4

from tests.modules.card_hub.conftest import ORG_ID, cliente_row

CPF_1 = "111.444.777-35"
CPF_2 = "529.982.247-25"


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


def _atendimento(aid: str, cliente_id: str) -> dict:
    return {
        "id": aid, "org_id": ORG_ID, "cliente_id": cliente_id, "lead_id": None,
        "meta_ads_lead_id": None, "status": "aberta", "substituida_por": None,
        "arquivado": False, "titulo": "Compra do apto",
        "created_at": "2026-01-01T00:00:00+00:00", "closed_at": None,
    }


def _contrato_row(contrato_id: str, aid: str) -> dict:
    return {
        "id": contrato_id, "org_id": ORG_ID, "atendimento_id": aid,
        "titulo": "Contrato", "modelo": "compra_venda", "status": "rascunho",
        "status_em": None, "status_por": None, "origem": "upload", "criado_por": None,
        "deleted_at": None, "delete_motivo": None, "delete_solicitado_por": None,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": None,
        "assinatura_data": None, "prazo_pendencias_dias": None,
    }


def _testemunha_row(*, nome: str, cpf: str | None, org_id: str = ORG_ID) -> dict:
    return {
        "id": str(uuid4()), "org_id": org_id, "nome": nome, "cpf": cpf,
        "rg": None, "email": None, "celular": None,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": None,
    }


def _seed(scoped) -> dict:
    cid, aid, contrato_id = str(uuid4()), str(uuid4()), str(uuid4())
    scoped.set_table_data("clientes", [cliente_row(cid, nome="Luciano")])
    scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
    scoped.set_table_data("atendimento_contratos", [_contrato_row(contrato_id, aid)])
    scoped.set_table_data("contrato_testemunhas", [])
    return {"cliente": cid, "atendimento": aid, "contrato": contrato_id}


def _url(ids: dict) -> str:
    return f"/api/clientes/{ids['cliente']}/contratos/{ids['contrato']}/testemunhas"


class TestListing:
    def test_a_fresh_contract_has_no_selection(self, client, scoped):
        ids = _seed(scoped)
        r = client.get(_url(ids), headers=_auth())
        assert r.status_code == 200, r.text
        assert r.json() == {"items": [], "total": 0}

    def test_an_unknown_contract_is_404(self, client, scoped):
        ids = _seed(scoped)
        r = client.get(
            f"/api/clientes/{ids['cliente']}/contratos/{uuid4()}/testemunhas",
            headers=_auth(),
        )
        assert r.status_code == 404


class TestDefinir:
    def test_selecting_two_witnesses_round_trips_in_order(self, client, scoped):
        ids = _seed(scoped)
        t1 = _testemunha_row(nome="Ana", cpf=CPF_1)
        t2 = _testemunha_row(nome="Beto", cpf=CPF_2)
        scoped.set_table_data("org_testemunhas", [t1, t2])

        r = client.put(_url(ids), json={"testemunha_ids": [t2["id"], t1["id"]]}, headers=_auth())
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 2
        assert [item["testemunha"]["nome"] for item in body["items"]] == ["Beto", "Ana"]
        assert [item["ordem"] for item in body["items"]] == [1, 2]

        listado = client.get(_url(ids), headers=_auth()).json()
        assert [item["testemunha"]["id"] for item in listado["items"]] == [t2["id"], t1["id"]]

    def test_replacing_the_selection_drops_the_old_one(self, client, scoped):
        ids = _seed(scoped)
        t1 = _testemunha_row(nome="Ana", cpf=CPF_1)
        t2 = _testemunha_row(nome="Beto", cpf=CPF_2)
        scoped.set_table_data("org_testemunhas", [t1, t2])

        client.put(_url(ids), json={"testemunha_ids": [t1["id"]]}, headers=_auth())
        r = client.put(_url(ids), json={"testemunha_ids": [t2["id"]]}, headers=_auth())
        assert r.status_code == 200, r.text
        listado = client.get(_url(ids), headers=_auth()).json()
        assert listado["total"] == 1
        assert listado["items"][0]["testemunha"]["nome"] == "Beto"

    def test_clearing_the_selection(self, client, scoped):
        ids = _seed(scoped)
        t1 = _testemunha_row(nome="Ana", cpf=CPF_1)
        scoped.set_table_data("org_testemunhas", [t1])
        client.put(_url(ids), json={"testemunha_ids": [t1["id"]]}, headers=_auth())

        r = client.put(_url(ids), json={"testemunha_ids": []}, headers=_auth())
        assert r.status_code == 200, r.text
        assert r.json() == {"items": [], "total": 0}

    def test_a_duplicate_id_is_refused_with_400(self, client, scoped):
        ids = _seed(scoped)
        t1 = _testemunha_row(nome="Ana", cpf=CPF_1)
        scoped.set_table_data("org_testemunhas", [t1])

        r = client.put(
            _url(ids), json={"testemunha_ids": [t1["id"], t1["id"]]}, headers=_auth()
        )
        assert r.status_code == 400, r.text
        assert r.json()["error"]["code"] == "TESTEMUNHA_SELECIONADA_INVALIDA"

    def test_an_unknown_testemunha_id_is_404(self, client, scoped):
        ids = _seed(scoped)
        scoped.set_table_data("org_testemunhas", [])

        r = client.put(_url(ids), json={"testemunha_ids": [str(uuid4())]}, headers=_auth())
        assert r.status_code == 404

    def test_a_testemunha_from_another_org_is_404(self, client, scoped):
        ids = _seed(scoped)
        alheia = _testemunha_row(nome="De Outra Org", cpf=CPF_1, org_id=str(uuid4()))
        scoped.set_table_data("org_testemunhas", [alheia])

        r = client.put(_url(ids), json={"testemunha_ids": [alheia["id"]]}, headers=_auth())
        assert r.status_code == 404

    def test_a_cpf_pendente_witness_is_refused_with_400(self, client, scoped):
        """Defense in depth (migration 168 header) — the FE only offers
        CPF-complete witnesses, but the server re-validates regardless."""
        ids = _seed(scoped)
        pendente = _testemunha_row(nome="CPF Pendente", cpf=None)
        scoped.set_table_data("org_testemunhas", [pendente])

        r = client.put(_url(ids), json={"testemunha_ids": [pendente["id"]]}, headers=_auth())
        assert r.status_code == 400, r.text
        assert r.json()["error"]["code"] == "TESTEMUNHA_SELECIONADA_INVALIDA"
        assert "CPF pendente" in r.json()["error"]["message"]

    def test_an_unknown_contract_is_404(self, client, scoped):
        ids = _seed(scoped)
        r = client.put(
            f"/api/clientes/{ids['cliente']}/contratos/{uuid4()}/testemunhas",
            json={"testemunha_ids": []},
            headers=_auth(),
        )
        assert r.status_code == 404


CPF_3 = "935.411.347-80"
CPF_4 = "390.533.447-05"
CPF_5 = "123.456.789-09"
CPF_6 = "987.654.321-00"


class TestLimitesESoftDelete:
    """Owner decisions (2026-09-24): at most 5 witnesses per contract; a
    witness removed from the registry stays on contracts that already
    selected it, but cannot be newly added to one."""

    def test_more_than_five_witnesses_is_refused_with_400(self, client, scoped):
        ids = _seed(scoped)
        linhas = [
            _testemunha_row(nome=f"T{i}", cpf=cpf)
            for i, cpf in enumerate([CPF_1, CPF_2, CPF_3, CPF_4, CPF_5, CPF_6])
        ]
        scoped.set_table_data("org_testemunhas", linhas)
        r = client.put(
            _url(ids), json={"testemunha_ids": [t["id"] for t in linhas]}, headers=_auth()
        )
        assert r.status_code == 400, r.text

    def test_a_deleted_witness_already_selected_is_kept_and_flagged(self, client, scoped):
        ids = _seed(scoped)
        t1 = _testemunha_row(nome="Ana", cpf=CPF_1)
        t2 = _testemunha_row(nome="Beto", cpf=CPF_2)
        scoped.set_table_data("org_testemunhas", [t1, t2])
        client.put(_url(ids), json={"testemunha_ids": [t1["id"], t2["id"]]}, headers=_auth())

        scoped.table("org_testemunhas").update(
            {"excluida_em": "2026-09-24T00:00:00+00:00"}
        ).eq("id", t1["id"]).execute()

        listado = client.get(_url(ids), headers=_auth()).json()
        assert [i["testemunha"]["nome"] for i in listado["items"]] == ["Ana", "Beto"]
        assert listado["items"][0]["testemunha"]["excluida"] is True

        # Re-saving the same contract keeps her.
        r = client.put(
            _url(ids), json={"testemunha_ids": [t1["id"], t2["id"]]}, headers=_auth()
        )
        assert r.status_code == 200, r.text

    def test_a_deleted_witness_cannot_be_added_to_another_contract(self, client, scoped):
        ids = _seed(scoped)
        t1 = _testemunha_row(nome="Ana", cpf=CPF_1)
        t1["excluida_em"] = "2026-09-24T00:00:00+00:00"
        scoped.set_table_data("org_testemunhas", [t1])

        r = client.put(_url(ids), json={"testemunha_ids": [t1["id"]]}, headers=_auth())
        assert r.status_code == 400, r.text
