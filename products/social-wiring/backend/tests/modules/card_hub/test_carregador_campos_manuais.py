"""Migration 306 — what an operator TYPES on the imóvel page reaches the
contract through the real loader (`carregador.carregar`), never only what a
document upload produced (owner directive 2026-10-24).

- the typed IMÓVEL: description WINS over the matrícula's derived
  `descricao_imovel` block, carrying no formatting ranges (they index the
  derived text, not the typed one);
- a certidão typed with no file is an imóvel certidão of the contract
  (`documento_id is None`);
- typed sellers' names are the last transfer's `transmitentes`.

All data is synthetic.
"""
from __future__ import annotations

from uuid import UUID, uuid4

from app.modules.card_hub.contrato_gerador import carregador
from tests.modules.card_hub.conftest import ORG_ID
from tests.modules.card_hub.test_contrato_gerador_endpoints import _T0, _rows, _seed_completo

DESCRICAO_TIPADA = "Casa ficticia nº 7 do Loteamento Exemplo, com 300,00 m² de terreno."


def _carregar(scoped, ids):
    dados, _ = carregador.carregar(
        scoped, UUID(ORG_ID), UUID(ids["cliente"]), UUID(ids["contrato"]), usuario_id=None
    )
    return dados


def _dados_ex001(scoped, **campos) -> None:
    linhas = _rows(scoped, "imovel_dados")
    alvo = next(r for r in linhas if r["codigo"] == "EX001")
    alvo.update(campos)
    scoped.set_table_data("imovel_dados", linhas)


class TestCarregadorCamposManuais:
    def test_the_derived_description_answers_until_one_is_typed(self, client, scoped):
        ids = _seed_completo(scoped)
        derivado = _carregar(scoped, ids).matricula.descricao_imovel_texto

        _dados_ex001(
            scoped,
            descricao_imovel_texto=DESCRICAO_TIPADA,
            descricao_imovel_confirmado_por=str(uuid4()),
            descricao_imovel_confirmado_em=_T0,
        )
        matricula = _carregar(scoped, ids).matricula
        assert matricula.descricao_imovel_texto == DESCRICAO_TIPADA != derivado
        assert matricula.descricao_imovel_formatacao == ()

    def test_a_certidao_typed_with_no_file_reaches_the_contract(self, client, scoped):
        ids = _seed_completo(scoped)
        scoped.set_table_data("imovel_certidoes_manuais", [{
            "id": str(uuid4()), "org_id": ORG_ID, "codigo": "EX001", "tipo": "cnd_condominio",
            "numero": None, "emitida_em": "2099-01-01", "validade_ate": None,
            "resultado": "negativa", "inscricao_imobiliaria": None,
            "confirmado_por": None, "confirmado_em": "2099-01-01T00:00:00+00:00", "created_at": _T0,
        }])
        certidoes = {c.tipo: c for c in _carregar(scoped, ids).imovel.certidoes}
        cnd = certidoes["cnd_condominio"]
        assert (cnd.documento_id, cnd.resultado, cnd.confirmado) == (None, "negativa", True)
        assert cnd.emitida_em.isoformat() == "2099-01-01"

    def test_typed_sellers_are_the_last_transfers_transmitentes(self, client, scoped):
        ids = _seed_completo(scoped)
        _dados_ex001(
            scoped,
            ultima_transferencia_manual_transmitentes=["Fulano Ficticio", "Beltrana Ficticia"],
            ultima_transferencia_manual_confirmado_em=_T0,
        )
        imovel = _carregar(scoped, ids).imovel
        assert imovel.ultima_transferencia_transmitentes == ("Fulano Ficticio", "Beltrana Ficticia")
