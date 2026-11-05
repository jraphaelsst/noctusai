"""Security M1: identity read from a document a lead sent over WhatsApp is not printed in a contract until a human
confirms it. `carregador.identidade_nao_verificada` decides per field from the provenance columns; readiness
(`derivacao`) blocks with `IDENTIDADE_NAO_VERIFICADA`. Synthetic data only."""
from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest
from noctusai_lib.testing import MockSupabaseClient

from app.modules.card_hub.contrato_gerador import carregador, derivacao
from tests.modules.card_hub import contrato_gerador_fixtures as fx

ORG = uuid4()
DOC = "00000000-0000-4000-8000-0000000000d1"


def _cliente(**over):
    row = {"cpf": "11144477735", "rg": "12.345.678-9", "rg_orgao_expedidor": "SSP/SP",
           "cpf_documento_id": DOC, "rg_documento_id": DOC, "rg_orgao_expedidor_documento_id": DOC}
    row.update(over)
    return row


def _db(**doc):
    db = MockSupabaseClient()
    db.set_table_data("cliente_documentos", [{"id": DOC, "org_id": str(ORG), "origem_entrada": "whatsapp", **doc}])
    return db


class TestCarregador:
    def test_whatsapp_extraction_without_a_human_confirmation_is_unverified(self):
        assert carregador.identidade_nao_verificada(_db(), ORG, _cliente()) == ["cpf", "rg", "rg_orgao_expedidor"]

    def test_a_human_confirmation_per_field_clears_that_field(self):
        row = _cliente(cpf_confirmado_por=str(uuid4()), rg_confirmado_em="2026-11-03T10:00:00+00:00")
        assert carregador.identidade_nao_verificada(_db(), ORG, row) == ["rg_orgao_expedidor"]

    def test_an_upload_origin_document_is_not_flagged(self):
        assert carregador.identidade_nao_verificada(_db(origem_entrada="upload"), ORG, _cliente()) == []

    def test_a_typed_value_has_no_document_and_is_not_flagged(self):
        assert carregador.identidade_nao_verificada(_db(), ORG, _cliente(cpf_documento_id=None, rg_documento_id=None,
                                                                        rg_orgao_expedidor_documento_id=None)) == []

    def test_an_empty_value_is_not_flagged(self):
        assert carregador.identidade_nao_verificada(_db(), ORG, _cliente(rg=None, rg_orgao_expedidor=None)) == ["cpf"]

    def test_the_explicit_verificado_flag_wins_either_way(self):
        # flag false on an upload-origin document: unverified
        assert carregador.identidade_nao_verificada(_db(origem_entrada="upload", verificado=False), ORG, _cliente()) != []
        # flag true on a whatsapp document: verified
        assert carregador.identidade_nao_verificada(_db(verificado=True), ORG, _cliente()) == []
        # cliente-level flag
        row = _cliente(cpf_verificado=True)
        assert "cpf" not in carregador.identidade_nao_verificada(_db(), ORG, row)
        row = _cliente(cpf_verificado=False)
        assert "cpf" in carregador.identidade_nao_verificada(_db(origem_entrada="upload"), ORG, row)


class TestProntidao:
    def _avaliar(self, nao_verificada):
        d = fx.variante(1)
        d = replace(d, compradores=[replace(d.compradores[0], identidade_nao_verificada=nao_verificada), *d.compradores[1:]])
        pol = fx.politica_variante(1)
        sw = derivacao.derivar_switches(d, pol, fx.REFERENCIA)
        return derivacao.avaliar(d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)

    def test_an_unverified_identity_blocks_the_contract(self):
        av = self._avaliar(["cpf", "rg"])
        assert not av.pronto
        b = [x for x in av.bloqueios if x["codigo"] == "IDENTIDADE_NAO_VERIFICADA"]
        assert len(b) == 1 and "CPF" in b[0]["mensagem"] and "RG" in b[0]["mensagem"] and "WhatsApp" in b[0]["mensagem"]

    def test_a_verified_identity_does_not(self):
        av = self._avaliar([])
        assert av.pronto and not [x for x in av.bloqueios if x["codigo"] == "IDENTIDADE_NAO_VERIFICADA"]
