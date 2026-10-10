"""Proprietários (contract §4.2) — routes, `por_codigos`, and the matrícula
backfill (`origem="matricula"`)."""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from tests.modules.imovel_hub.conftest import ORG_ID, auth
from tests.modules.imovel_hub.relacionamentos_rows import (
    cliente_row,
    espelho,
    proprietario,
    registro,
    seed_tabelas,
)


def empresa_row(id_=None, *, cnpj="11222333000181", razao="ACME LTDA") -> dict:
    return {
        "id": id_ or str(uuid4()),
        "org_id": ORG_ID,
        "cnpj": cnpj,
        "razao_social": razao,
        "nome_fantasia": None,
    }


@pytest.fixture
def cenario(client, scoped):
    cliente = cliente_row(cpf="123.456.789-09", nome_oficial="Ana Souza Oficial")
    empresa = empresa_row()
    seed_tabelas(
        scoped,
        clientes=[cliente],
        empresas=[empresa],
        imovel_registry=[registro("ONE1"), registro("ONE2")],
        imoveis=[espelho("ONE1")],
        imovel_dados=[],
        imovel_proprietarios=[],
    )
    return {"cliente": cliente, "empresa": empresa, "scoped": scoped}


def curl(c):
    return f"/api/clientes/{c['cliente']['id']}/propriedades"


def eurl(c):
    return f"/api/empresas/{c['empresa']['id']}/propriedades"


ITEM_KEYS = {"id", "codigo", "origem", "created_at", "created_by", "imovel"}


class TestPropriedadesRoutes:
    def test_post_get_roundtrip_for_cliente(self, client, cenario):
        resp = client.post(curl(cenario), json={"codigo": "one1"}, headers=auth())
        assert resp.status_code == 201, resp.text
        assert set(resp.json()) == ITEM_KEYS and resp.json()["origem"] == "manual"
        body = client.get(curl(cenario), headers=auth()).json()
        assert set(body) == {"items", "total"} and body["total"] == 1
        assert body["items"][0]["codigo"] == "ONE1"

    def test_empresa_side_symmetrical(self, client, cenario):
        assert client.post(eurl(cenario), json={"codigo": "ONE2"}, headers=auth()).status_code == 201
        assert client.get(eurl(cenario), headers=auth()).json()["total"] == 1
        # and the cliente side stays empty
        assert client.get(curl(cenario), headers=auth()).json()["total"] == 0

    def test_duplicate_409_and_unknown_404(self, client, cenario):
        client.post(curl(cenario), json={"codigo": "ONE1"}, headers=auth())
        dup = client.post(curl(cenario), json={"codigo": "ONE1"}, headers=auth())
        assert dup.status_code == 409
        assert dup.json()["error"]["message"] == "Este imóvel já consta como propriedade."
        nf = client.post(curl(cenario), json={"codigo": "ZZ"}, headers=auth())
        assert nf.status_code == 404
        assert nf.json()["error"]["message"] == (
            "Imóvel ZZ não encontrado. Selecione um imóvel do catálogo ou cadastre-o."
        )

    def test_unknown_cliente_and_empresa_404(self, client, cenario):
        assert client.get(f"/api/clientes/{uuid4()}/propriedades", headers=auth()).status_code == 404
        assert client.get(f"/api/empresas/{uuid4()}/propriedades", headers=auth()).status_code == 404

    def test_delete_manual_is_204_soft(self, client, cenario):
        item = client.post(curl(cenario), json={"codigo": "ONE1"}, headers=auth()).json()
        assert client.delete(f"{curl(cenario)}/{item['id']}", headers=auth()).status_code == 204
        assert client.get(curl(cenario), headers=auth()).json()["total"] == 0
        assert len(cenario["scoped"].table("imovel_proprietarios").select("*").execute().data) == 1

    @pytest.mark.parametrize("origem", ["matricula", "atendimento"])
    def test_derived_rows_cannot_be_removed(self, client, cenario, origem):
        row = proprietario("ONE1", cliente_id=cenario["cliente"]["id"], origem=origem)
        cenario["scoped"].set_table_data("imovel_proprietarios", [row])
        resp = client.delete(f"{curl(cenario)}/{row['id']}", headers=auth())
        assert resp.status_code == 409
        err = resp.json()["error"]
        assert err["code"] == "PROPRIEDADE_DERIVADA"
        assert err["message"] == (
            "Esta propriedade foi registrada automaticamente. "
            "Corrija a matrícula/negociação de origem."
        )

    def test_delete_of_another_owners_row_is_404(self, client, cenario):
        row = proprietario("ONE1", empresa_id=cenario["empresa"]["id"])
        cenario["scoped"].set_table_data("imovel_proprietarios", [row])
        assert client.delete(f"{curl(cenario)}/{row['id']}", headers=auth()).status_code == 404


class TestImovelSide:
    def test_exact_keys_pf_and_pj(self, client, cenario):
        cenario["scoped"].set_table_data(
            "imovel_proprietarios",
            [
                proprietario("ONE1", cliente_id=cenario["cliente"]["id"], origem="matricula",
                             created_at="2026-01-01T00:00:00+00:00"),
                proprietario("ONE1", empresa_id=cenario["empresa"]["id"],
                             created_at="2026-01-02T00:00:00+00:00"),
                proprietario("ONE2", cliente_id=cenario["cliente"]["id"]),
            ],
        )
        resp = client.get("/api/imoveis/one1/proprietarios", headers=auth())
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body) == {"items", "total"} and body["total"] == 2
        pf, pj = body["items"]
        keys = {"id", "tipo_pessoa", "cliente_id", "empresa_id", "nome", "documento",
                "celular", "email", "origem", "fonte_codigo", "created_at"}
        assert set(pf) == keys and set(pj) == keys
        assert pf["tipo_pessoa"] == "PF" and pf["nome"] == "Ana Souza Oficial"
        assert pf["documento"] == "12345678909" and pf["celular"] == "+5511999990001"
        assert pj["tipo_pessoa"] == "PJ" and pj["empresa_id"] and pj["cliente_id"] is None
        assert pj["nome"] == "ACME LTDA" and pj["documento"] == "11222333000181"
        assert pj["celular"] is None and pj["email"] is None

    def test_unknown_codigo_404(self, client, cenario):
        assert client.get("/api/imoveis/NOPE/proprietarios", headers=auth()).status_code == 404

    def test_por_codigos_batched_and_canonical_keyed(self, client, cenario):
        from app.modules.imovel_hub import proprietarios_service as svc

        cenario["scoped"].set_table_data(
            "imovel_proprietarios",
            [
                proprietario("ONE1", cliente_id=cenario["cliente"]["id"]),
                proprietario("ONE1", empresa_id=cenario["empresa"]["id"], deleted_at="2026-03-01T00:00:00+00:00"),
            ],
        )
        out = svc.por_codigos(cenario["scoped"], UUID(ORG_ID), ["one1", "ONE2", ""])
        assert out == {"ONE1": [{"nome": "Ana Souza Oficial", "documento": "12345678909", "tipo_pessoa": "PF"}]}
        assert svc.por_codigos(cenario["scoped"], UUID(ORG_ID), []) == {}


class TestMatriculaBackfill:
    """`run_backfill_matricula` — the Python half of migration 183."""

    CPF = "12345678909"

    def _seed(self, cenario, *, adquirentes, natureza="compra_e_venda", cliente_extra=None):
        scoped = cenario["scoped"]
        eid, ato_ant, ato_ult = str(uuid4()), str(uuid4()), str(uuid4())
        seed_tabelas(
            scoped,
            matricula_extracoes=[
                {"id": eid, "org_id": ORG_ID, "codigo": "one1", "status": "concluida",
                 "created_at": "2026-01-01T00:00:00+00:00"},
                # a newer but NOT concluded extraction must be ignored
                {"id": str(uuid4()), "org_id": ORG_ID, "codigo": "ONE2", "status": "processando",
                 "created_at": "2026-02-01T00:00:00+00:00"},
            ],
            matricula_atos=[
                {"id": ato_ant, "org_id": ORG_ID, "extracao_id": eid, "ordem": 1, "kind": "R"},
                {"id": ato_ult, "org_id": ORG_ID, "extracao_id": eid, "ordem": 2, "kind": "R"},
            ],
            matricula_ato_detalhes=[
                {"id": str(uuid4()), "org_id": ORG_ID, "extracao_id": eid, "ato_id": ato_ant,
                 "natureza": "compra_e_venda", "adquirentes": [{"nome": "Antigo", "cpf_cnpj": "52998224725"}]},
                {"id": str(uuid4()), "org_id": ORG_ID, "extracao_id": eid, "ato_id": ato_ult,
                 "natureza": natureza, "adquirentes": adquirentes},
            ],
            matricula_qualificacoes=[],
            imovel_proprietarios=[],
        )
        return eid

    def _run(self, cenario, **kw):
        from app.modules.imovel_hub import proprietarios_service as svc

        return svc.run_backfill_matricula(cenario["scoped"], UUID(ORG_ID), **kw)

    def test_matches_the_last_transfers_adquirentes_by_cpf(self, client, cenario):
        self._seed(cenario, adquirentes=[{"nome": "Ana", "cpf_cnpj": "123.456.789-09"}])
        out = self._run(cenario)
        assert out["criados"] == 1 and out["vinculados_cliente"] == 1
        rows = cenario["scoped"].table("imovel_proprietarios").select("*").execute().data
        assert [(r["codigo"], r["cliente_id"], r["origem"]) for r in rows] == [
            ("ONE1", cenario["cliente"]["id"], "matricula")
        ]
        # the OLDER act's adquirente (52998224725) was never considered
        assert out["adquirentes"] == 1

    def test_is_idempotent(self, client, cenario):
        self._seed(cenario, adquirentes=[{"nome": "Ana", "cpf_cnpj": self.CPF}])
        self._run(cenario)
        second = self._run(cenario)
        assert second["criados"] == 0 and second["ja_existentes"] == 1
        assert len(cenario["scoped"].table("imovel_proprietarios").select("*").execute().data) == 1

    def test_dry_run_writes_nothing_but_reports(self, client, cenario):
        self._seed(cenario, adquirentes=[{"nome": "Ana", "cpf_cnpj": self.CPF}])
        out = self._run(cenario, dry_run=True)
        assert out["dry_run"] is True and out["criados"] == 1
        assert cenario["scoped"].table("imovel_proprietarios").select("*").execute().data == []

    def test_removed_pair_is_not_resurrected(self, client, cenario):
        self._seed(cenario, adquirentes=[{"nome": "Ana", "cpf_cnpj": self.CPF}])
        cenario["scoped"].set_table_data(
            "imovel_proprietarios",
            [proprietario("ONE1", cliente_id=cenario["cliente"]["id"], origem="matricula",
                          deleted_at="2026-03-01T00:00:00+00:00")],
        )
        out = self._run(cenario)
        assert out["criados"] == 0 and out["ja_existentes"] == 1

    def test_empresa_matched_by_cnpj(self, client, cenario):
        self._seed(cenario, adquirentes=[{"nome": "ACME", "cpf_cnpj": "11.222.333/0001-81"}])
        out = self._run(cenario)
        assert out["vinculados_empresa"] == 1
        row = cenario["scoped"].table("imovel_proprietarios").select("*").execute().data[0]
        assert row["empresa_id"] == cenario["empresa"]["id"] and row["cliente_id"] is None

    def test_ambiguous_and_unmatched_are_counted_never_guessed(self, client, cenario):
        gemeo = cliente_row(nome="Gêmeo", cpf=self.CPF)
        cenario["scoped"].set_table_data("clientes", [cenario["cliente"], gemeo])
        self._seed(cenario, adquirentes=[
            {"nome": "Ana", "cpf_cnpj": self.CPF},
            {"nome": "Ninguém", "cpf_cnpj": "52998224725"},
        ])
        out = self._run(cenario)
        assert out["ambiguos"] == 1 and out["sem_correspondencia"] == 1 and out["criados"] == 0

    def test_vinculada_qualificacao_resolves_an_ambiguous_cpf(self, client, cenario):
        gemeo = cliente_row(nome="Gêmeo", cpf=self.CPF)
        cenario["scoped"].set_table_data("clientes", [cenario["cliente"], gemeo])
        eid = self._seed(cenario, adquirentes=[{"nome": "Ana", "cpf_cnpj": self.CPF}])
        cenario["scoped"].set_table_data(
            "matricula_qualificacoes",
            [{"id": str(uuid4()), "org_id": ORG_ID, "extracao_id": eid,
              "cpf_cnpj_normalizado": self.CPF, "cliente_id": gemeo["id"], "vinculo_status": "vinculado"}],
        )
        out = self._run(cenario)
        assert out["criados"] == 1
        row = cenario["scoped"].table("imovel_proprietarios").select("*").execute().data[0]
        assert row["cliente_id"] == gemeo["id"]

    def test_non_transfer_natureza_is_skipped(self, client, cenario):
        self._seed(cenario, adquirentes=[{"nome": "Ana", "cpf_cnpj": self.CPF}], natureza="hipoteca")
        # the OLDER compra_e_venda act is then the last transfer (Antigo, unmatched)
        out = self._run(cenario)
        assert out["criados"] == 0 and out["sem_correspondencia"] == 1

    def _sync(self, cenario, eid):
        from app.modules.imovel_hub import proprietarios_service as svc

        return svc.sincronizar_da_extracao(cenario["scoped"], UUID(ORG_ID), eid)

    def test_sync_one_extraction_populates_current_owner_and_spouse(self, client, cenario):
        conjuge = cliente_row(nome="Cônjuge", cpf="529.982.247-25")
        cenario["scoped"].set_table_data("clientes", [cenario["cliente"], conjuge])
        eid = self._seed(cenario, adquirentes=[
            {"nome": "Ana", "cpf_cnpj": "123.456.789-09"},
            {"nome": "Cônjuge", "cpf_cnpj": "529.982.247-25"},
        ])
        out = self._sync(cenario, eid)
        assert out["status"] == "ok" and out["criados"] == 2
        rows = cenario["scoped"].table("imovel_proprietarios").select("*").execute().data
        assert sorted(r["cliente_id"] for r in rows) == sorted(
            [cenario["cliente"]["id"], conjuge["id"]]
        )
        assert {r["origem"] for r in rows} == {"matricula"}
        assert {r["codigo"] for r in rows} == {"ONE1"}

    def test_sync_one_extraction_is_idempotent_and_respects_removals(self, client, cenario):
        eid = self._seed(cenario, adquirentes=[{"nome": "Ana", "cpf_cnpj": self.CPF}])
        self._sync(cenario, eid)
        assert self._sync(cenario, eid)["criados"] == 0
        assert len(cenario["scoped"].table("imovel_proprietarios").select("*").execute().data) == 1

    def test_sync_one_extraction_counts_unmatched_never_guesses(self, client, cenario):
        eid = self._seed(cenario, adquirentes=[{"nome": "Ninguém", "cpf_cnpj": "52998224725"}])
        out = self._sync(cenario, eid)
        assert out["criados"] == 0 and out["sem_correspondencia"] == 1

    def test_sync_one_extraction_without_transfer_does_nothing(self, client, cenario):
        eid = self._seed(cenario, adquirentes=[], natureza="hipoteca")
        cenario["scoped"].set_table_data("matricula_ato_detalhes", [])
        out = self._sync(cenario, eid)
        assert out["status"] == "sem_transferencia"

    def test_sync_one_extraction_unknown_or_not_concluded(self, client, cenario):
        self._seed(cenario, adquirentes=[])
        assert self._sync(cenario, str(uuid4()))["status"] == "nao_encontrada"

    def test_cli_main_dry_run_prints_counts_only(self, client, cenario, capsys):
        """The documented entrypoint; asserts NO personal data in its output."""
        from app.modules.imovel_hub import proprietarios_service as svc

        self._seed(cenario, adquirentes=[{"nome": "Ana Secreta", "cpf_cnpj": self.CPF}])
        rc = svc.main(["backfill-matricula", "--org", ORG_ID, "--dry-run"])
        out = capsys.readouterr().out
        assert rc == 0
        assert '"criados": 1' in out and '"dry_run": true' in out
        assert "Ana Secreta" not in out and self.CPF not in out


class TestReconcileDeAtendimentos:
    def test_vendedor_parte_x_negociacao_imovel(self, client, cenario):
        from app.modules.imovel_hub import proprietarios_service as svc
        from tests.modules.imovel_hub.relacionamentos_rows import atendimento_row

        at = atendimento_row(cliente_id=None)
        seed_tabelas(
            cenario["scoped"],
            atendimentos=[at],
            atendimento_negociacao=[{"org_id": ORG_ID, "atendimento_id": at["id"], "imovel_codigo": "ONE1"}],
            atendimento_partes=[
                {"id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": at["id"],
                 "cliente_id": cenario["cliente"]["id"], "empresa_id": None, "lado": "vendedor",
                 "papel": "vendedor", "created_at": "2026-02-01T00:00:00+00:00"},
                {"id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": at["id"],
                 "cliente_id": str(uuid4()), "empresa_id": None, "lado": "comprador",
                 "papel": "comprador", "created_at": "2026-02-01T00:00:00+00:00"},
            ],
        )
        out = svc.reconcile_de_atendimentos(cenario["scoped"], UUID(ORG_ID))
        assert out == {"criados": 1}
        row = cenario["scoped"].table("imovel_proprietarios").select("*").execute().data[0]
        assert (row["codigo"], row["cliente_id"], row["origem"]) == ("ONE1", cenario["cliente"]["id"], "atendimento")
        assert svc.reconcile_de_atendimentos(cenario["scoped"], UUID(ORG_ID)) == {"criados": 0}
