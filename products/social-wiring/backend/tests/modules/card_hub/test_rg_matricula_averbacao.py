"""A CNH-only RG completes itself from a matrícula averbação (item 3).

The CNH prints the RG without its check digit; when the imóvel's matrícula
states "RG … 52.179.965-X … CPF 412.954.238-98" for THIS cliente (same CPF,
prefix = the CNH number) the full RG is persisted with
`rg_origem='matricula_averbacao'` and the checklist ressalva drops — no human
click. Synthetic numbers.
"""
from __future__ import annotations

from uuid import UUID, uuid4

from app.modules.card_hub import rg_matricula_service as svc
from tests.modules.card_hub import test_documento_checklist_derivacao as base
from tests.modules.card_hub.conftest import ORG_ID, cliente_row
from tests.modules.matriculas.conftest import CODIGO, extracao_row, registry_row

CPF = "412.954.238-98"


def _texto(rg="52.179.965-X", cpf=CPF) -> str:
    return (
        "MATRÍCULA Nº 999\nTerreno ficticio.\n"
        f"AV-4/999 - Em 05/05/2021. Averba-se que o número do RG de FILHO UM FICTICIO é {rg} "
        f"e o do CPF é {cpf}, conforme requerimento.\n"
    )


def _cenario(scoped, *, texto, rg="52179965", origem="cnh", via="proprietario", **extra):
    cid = str(uuid4())
    scoped.set_table_data(
        "clientes",
        [cliente_row(cid, nome_oficial="Filho Um Ficticio", rg=rg, rg_origem=origem,
                     rg_orgao_expedidor="SSP-SP", cpf=CPF, **extra)],
    )
    scoped.set_table_data("cliente_documento_checklist", [])
    scoped.set_table_data("cliente_documentos", [])
    scoped.set_table_data("imovel_registry", [registry_row()])
    scoped.set_table_data("matricula_extracoes", [extracao_row(texto=texto)])
    scoped.set_table_data("matricula_atos", [])
    scoped.set_table_data("matricula_ato_detalhes", [])
    scoped.set_table_data("imovel_dados", [])
    scoped.set_table_data("atendimentos", [])
    scoped.set_table_data("atendimento_partes", [])
    scoped.set_table_data("atendimento_negociacao", [])
    scoped.set_table_data(
        "imovel_proprietarios",
        [{"id": str(uuid4()), "org_id": ORG_ID, "codigo": CODIGO, "cliente_id": cid,
          "origem": "matricula", "deleted_at": None}],
    )
    return cid


def _row(scoped, cid):
    return next(r for r in scoped.table("clientes").select("*").execute().data if r["id"] == cid)


class TestCompletarRg:
    def test_unique_match_persists_the_full_rg_with_its_origin(self, client, scoped):
        cid = _cenario(scoped, texto=_texto())
        row = svc.completar(scoped, UUID(ORG_ID), UUID(cid), _row(scoped, cid))
        assert row["rg"] == "52.179.965-X" and row["rg_origem"] == "matricula_averbacao"
        gravado = _row(scoped, cid)
        assert gravado["rg"] == "52.179.965-X" and gravado["rg_origem"] == "matricula_averbacao"

    def test_the_checklist_ressalva_drops_by_itself(self, client, scoped):
        cid = _cenario(scoped, texto=_texto())
        item = base._items(client, cid)["identidade"]
        assert item["concluido"] is True
        assert not item.get("ressalvas")

    def test_without_an_averbacao_the_ressalva_stays(self, client, scoped):
        cid = _cenario(scoped, texto="MATRÍCULA Nº 999\nTerreno ficticio.\n")
        item = base._items(client, cid)["identidade"]
        assert item["ressalvas"] == {"rg": "rg_so_da_cnh"}
        assert _row(scoped, cid)["rg"] == "52179965"

    def test_another_cpf_completes_nothing(self, client, scoped):
        cid = _cenario(scoped, texto=_texto(cpf="529.982.247-25"))
        item = base._items(client, cid)["identidade"]
        assert item["ressalvas"] == {"rg": "rg_so_da_cnh"}

    def test_a_printed_dv_that_fails_its_own_check_is_not_written(self, client, scoped):
        cid = _cenario(scoped, texto=_texto(rg="52.179.965-1"))
        assert svc.completar(scoped, UUID(ORG_ID), UUID(cid), _row(scoped, cid))["rg"] == "52179965"

    def test_an_rg_from_the_rg_card_or_confirmed_is_never_touched(self, client, scoped):
        cid = _cenario(scoped, texto=_texto(), origem="rg")
        assert svc.completar(scoped, UUID(ORG_ID), UUID(cid), _row(scoped, cid))["rg"] == "52179965"

    def test_the_imovel_is_found_through_the_deal_when_there_is_no_owner_row(self, client, scoped):
        cid = _cenario(scoped, texto=_texto())
        scoped.set_table_data("imovel_proprietarios", [])
        atendimento = str(uuid4())
        scoped.set_table_data("atendimentos", [{"id": atendimento, "org_id": ORG_ID, "cliente_id": cid}])
        scoped.set_table_data(
            "atendimento_negociacao",
            [{"atendimento_id": atendimento, "org_id": ORG_ID, "imovel_codigo": CODIGO}],
        )
        row = svc.completar(scoped, UUID(ORG_ID), UUID(cid), _row(scoped, cid))
        assert row["rg_origem"] == "matricula_averbacao" and row["rg"] == "52.179.965-X"
