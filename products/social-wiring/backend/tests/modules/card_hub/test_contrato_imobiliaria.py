"""`/api/clientes/{cliente_id}/contratos/{contrato_id}/imobiliaria` and the ONE
resolution rule (`imobiliarias_service.resolver`) — migration 215."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from tests.modules.card_hub.conftest import ORG_ID, cliente_row
from tests.modules.card_hub.test_contrato_testemunhas import _atendimento, _auth, _contrato_row

_T = "2026-01-01T00:00:00+00:00"


def _imobiliaria(*, razao="Empresa", cnpj="11222333000181", excluida=None, org_id=ORG_ID, created=_T) -> dict:
    return {
        "id": str(uuid4()), "org_id": org_id, "razao_social": razao, "nome_fantasia": None,
        "cnpj": cnpj, "responsavel_nome": "R", "responsavel_creci": "1", "endereco_cidade": "SP",
        "created_at": created, "updated_at": None, "excluida_em": excluida,
    }


def _seed(scoped, imobiliarias: list[dict], *, escolhida: str | None = None) -> dict:
    cid, aid, contrato_id = str(uuid4()), str(uuid4()), str(uuid4())
    scoped.set_table_data("clientes", [cliente_row(cid, nome="Luciano")])
    scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
    row = _contrato_row(contrato_id, aid)
    row["imobiliaria_id"] = escolhida
    scoped.set_table_data("atendimento_contratos", [row])
    scoped.set_table_data("org_imobiliarias", imobiliarias)
    return {"cliente": cid, "contrato": contrato_id}


def _url(ids: dict) -> str:
    return f"/api/clientes/{ids['cliente']}/contratos/{ids['contrato']}/imobiliaria"


class TestResolutionRule:
    def test_stored_choice_wins_origem_selecionada(self, client, scoped):
        a, b = _imobiliaria(razao="A"), _imobiliaria(razao="B", cnpj="06057235000104")
        ids = _seed(scoped, [a, b], escolhida=b["id"])
        r = client.get(_url(ids), headers=_auth())
        assert r.status_code == 200, r.text
        assert r.json()["origem"] == "selecionada"
        assert r.json()["imobiliaria"]["id"] == b["id"]
        assert r.json()["imobiliaria"]["excluida"] is False

    def test_a_soft_deleted_choice_is_still_returned_flagged(self, client, scoped):
        a = _imobiliaria(excluida=_T)
        ids = _seed(scoped, [a], escolhida=a["id"])
        body = client.get(_url(ids), headers=_auth()).json()
        assert body["origem"] == "selecionada" and body["imobiliaria"]["excluida"] is True

    def test_exactly_one_active_is_auto_selected(self, client, scoped):
        a = _imobiliaria()
        gone = _imobiliaria(razao="Velha", cnpj="06057235000104", excluida=_T)
        ids = _seed(scoped, [a, gone])
        body = client.get(_url(ids), headers=_auth()).json()
        assert body["origem"] == "unica" and body["imobiliaria"]["id"] == a["id"]

    def test_zero_or_many_active_resolves_to_nothing(self, client, scoped):
        ids = _seed(scoped, [])
        assert client.get(_url(ids), headers=_auth()).json() == {"imobiliaria": None, "origem": None}
        ids = _seed(scoped, [_imobiliaria(), _imobiliaria(cnpj="06057235000104")])
        assert client.get(_url(ids), headers=_auth()).json() == {"imobiliaria": None, "origem": None}

    def test_faltando_is_derived(self, client, scoped):
        a = _imobiliaria()
        a["responsavel_nome"] = None
        ids = _seed(scoped, [a])
        assert client.get(_url(ids), headers=_auth()).json()["imobiliaria"]["faltando"] == ["responsavel_nome"]


class TestPut:
    def test_put_stores_the_choice(self, client, scoped):
        a, b = _imobiliaria(), _imobiliaria(cnpj="06057235000104")
        ids = _seed(scoped, [a, b])
        r = client.put(_url(ids), json={"imobiliaria_id": b["id"]}, headers=_auth())
        assert r.status_code == 200, r.text
        assert r.json()["origem"] == "selecionada" and r.json()["imobiliaria"]["id"] == b["id"]
        stored = scoped.table("atendimento_contratos").select("*").eq("id", ids["contrato"]).execute().data[0]
        assert stored["imobiliaria_id"] == b["id"]

    def test_put_null_clears_the_choice(self, client, scoped):
        a, b = _imobiliaria(), _imobiliaria(cnpj="06057235000104")
        ids = _seed(scoped, [a, b], escolhida=a["id"])
        r = client.put(_url(ids), json={"imobiliaria_id": None}, headers=_auth())
        assert r.status_code == 200
        assert r.json() == {"imobiliaria": None, "origem": None}

    def test_unknown_or_foreign_company_is_404(self, client, scoped):
        foreign = _imobiliaria(org_id=str(uuid4()))
        ids = _seed(scoped, [foreign])
        for target in (str(uuid4()), foreign["id"]):
            assert client.put(_url(ids), json={"imobiliaria_id": target}, headers=_auth()).status_code == 404

    def test_choosing_a_soft_deleted_company_is_400_with_error_body(self, client, scoped):
        gone = _imobiliaria(razao="Velha Ltda", excluida=_T)
        ids = _seed(scoped, [gone, _imobiliaria(cnpj="06057235000104")])
        r = client.put(_url(ids), json={"imobiliaria_id": gone["id"]}, headers=_auth())
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "IMOBILIARIA_SELECIONADA_INVALIDA"
        assert r.json()["error"]["message"] == (
            "Velha Ltda foi removida do cadastro e não pode ser escolhida para um novo contrato."
        )

    def test_a_contract_already_holding_a_deleted_company_may_resave_it(self, client, scoped):
        gone = _imobiliaria(excluida=_T)
        ids = _seed(scoped, [gone], escolhida=gone["id"])
        assert client.put(_url(ids), json={"imobiliaria_id": gone["id"]}, headers=_auth()).status_code == 200

    def test_unknown_contract_is_404_and_extra_body_field_422(self, client, scoped):
        ids = _seed(scoped, [_imobiliaria()])
        other = f"/api/clientes/{ids['cliente']}/contratos/{uuid4()}/imobiliaria"
        assert client.get(other, headers=_auth()).status_code == 404
        assert client.put(_url(ids), json={"imobiliaria_id": None, "x": 1}, headers=_auth()).status_code == 422


class TestMigrationText:
    SQL = (Path(__file__).resolve().parents[3] / "migrations" / "215_org_imobiliarias.sql").read_text()

    def test_backfill_is_guarded_for_idempotence(self):
        assert "WHERE NOT EXISTS" in self.SQL
        assert "c.imobiliaria_id IS NULL" in self.SQL
        assert "CREATE TABLE IF NOT EXISTS" in self.SQL and "ADD COLUMN IF NOT EXISTS" in self.SQL

    def test_rls_is_org_picker_shaped_and_audited(self):
        for p in ("org_imobiliarias_select_own_org", "org_imobiliarias_write_own_org", "org_imobiliarias_service_role"):
            assert p in self.SQL
        assert "current_org_id_for('social_wiring')" in self.SQL
        assert "attach_acting_audit_triggers('social_wiring')" in self.SQL
