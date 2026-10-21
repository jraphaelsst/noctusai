"""Migration 300 — the contract generator reads the imóvel's condomínio LINK.

- `carregador`: the derived `em_condominio` (attached -> True, casa de rua ->
  False, neither -> the legacy 202 flag), `condominio_resposta`, and the
  empreendimento precedence (attached condomínio > manual text > CRM);
- `derivacao`: unanswered -> `falta` pointing at the imóvel page's control;
  legacy "em condomínio" with no link -> `aviso` only (nothing in flight
  breaks); answered -> nothing.

Pure functions over synthetic fixtures; `dados` mimics `dados_service.obter`.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from app.modules.card_hub.contrato_gerador import carregador, derivacao
from tests.modules.card_hub import contrato_gerador_fixtures as fx

COND = {"id": "c-1", "nome": "Residencial Vila Verde", "cidade": "Cotia", "bairro": None,
        "status_validacao": "validado"}


class TestCarregador:
    @pytest.mark.parametrize(
        "dados, esperado",
        [
            ({"condominio_id": "c-1", "em_condominio": True, "em_condominio_legado": None}, True),
            ({"casa_de_rua": True, "em_condominio": False, "em_condominio_legado": None}, False),
            ({"em_condominio": None, "em_condominio_legado": True}, True),
            ({"em_condominio": None, "em_condominio_legado": None}, None),
            # A link always wins over a stale legacy value.
            ({"casa_de_rua": True, "em_condominio": False, "em_condominio_legado": True}, False),
        ],
    )
    def test_em_condominio_derivation(self, dados, esperado):
        assert carregador._em_condominio(dados) is esperado

    @pytest.mark.parametrize(
        "dados, esperado",
        [
            ({"condominio_id": "c-1"}, "vinculado"),
            ({"casa_de_rua": True}, "casa_de_rua"),
            ({"casa_de_rua": False, "condominio_id": None}, None),
        ],
    )
    def test_condominio_resposta(self, dados, esperado):
        assert carregador._condominio_resposta(dados) == esperado

    def test_attached_condominio_name_wins_over_manual_and_crm(self):
        dados = {"condominio": COND, "empreendimento_manual": "Texto Livre"}
        assert carregador._empreendimento({"empreendimento": "CRM"}, dados) == "Residencial Vila Verde"

    def test_unlinked_keeps_the_158_precedence(self):
        assert carregador._empreendimento({"empreendimento": "CRM"}, {"empreendimento_manual": "Texto"}) == "Texto"
        assert carregador._empreendimento({"empreendimento": "CRM"}, {"condominio": None}) == "CRM"


def _avaliar(d):
    pol = fx.politica_variante(1)
    sw = derivacao.derivar_switches(d, pol, None)
    return derivacao.avaliar(d, sw, pol, fx.ASSINATURA, None)


def _imovel(**kw):
    d = fx.variante(1)
    return replace(d, imovel=replace(d.imovel, **kw))


class TestReadiness:
    def test_answered_fixtures_are_ready(self):
        assert _avaliar(fx.variante(1)).pronto
        av = _avaliar(_imovel(condominio_resposta="casa_de_rua", em_condominio=False))
        assert "imovel.condominio" not in [f["campo"] for f in av.faltando]

    def test_unanswered_is_a_falta_pointing_at_the_imovel_page_control(self):
        av = _avaliar(_imovel(condominio_resposta=None, em_condominio=None))
        item = next(f for f in av.faltando if f["campo"] == "imovel.condominio")
        assert item["rotulo"] == "Informe o condomínio do imóvel ou marque 'Casa de rua'"
        assert item["onde"] == "imovel"
        assert item["destino"]["tela"] == "imovel"
        assert item["destino"]["rota"] == f"/imoveis/{fx.variante(1).imovel.codigo}"
        assert item["destino"]["alvo"] == derivacao.ALVO_CONDOMINIO_DO_IMOVEL
        assert not av.pronto

    def test_legacy_em_condominio_without_link_is_an_aviso_not_a_block(self):
        av = _avaliar(_imovel(condominio_resposta=None, em_condominio=True))
        assert "imovel.condominio" not in [f["campo"] for f in av.faltando]
        aviso = next(a for a in av.avisos if a["codigo"] == "CONDOMINIO_NAO_VINCULADO")
        assert "Não bloqueia a geração" in aviso["mensagem"]
        assert av.pronto

    def test_legacy_explicit_false_is_answered(self):
        av = _avaliar(_imovel(condominio_resposta=None, em_condominio=False))
        assert "imovel.condominio" not in [f["campo"] for f in av.faltando]
        assert "CONDOMINIO_NAO_VINCULADO" not in [a["codigo"] for a in av.avisos]
