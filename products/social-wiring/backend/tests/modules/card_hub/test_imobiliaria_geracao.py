"""Signing-company generation behaviour (migration 215): região printing (D3),
the `imobiliaria.selecao` readiness gap, and the D4 non-blocking PIX aviso."""
from __future__ import annotations

from dataclasses import replace

from app.modules.card_hub.contrato_gerador import derivacao, frases
from app.modules.card_hub.contrato_gerador.dados import Favorecido
from tests.modules.card_hub import contrato_gerador_fixtures as fx


def _avaliar(d, n: int = 1):
    pol = fx.politica_variante(n)
    sw = derivacao.derivar_switches(d, pol, fx.REFERENCIA)
    return derivacao.avaliar(d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)


class TestRegiaoPrinting:
    def test_unset_regiao_leaves_the_text_exactly_as_before(self):
        org = fx.variante(1).imobiliaria
        assert org.creci_pj_regiao is None and org.responsavel_creci_regiao is None
        texto = frases.qualificacao_imobiliaria(org)
        assert "com inscrição no CRECI sob o nº 00001-J, neste ato" in texto
        assert "corretor de imóveis CRECI 000002-F, endereço" in texto
        assert "(" not in texto.split("CRECI", 1)[1].split("neste ato")[0]

    def test_each_regiao_prints_independently(self):
        base = fx.variante(1).imobiliaria
        so_pj = frases.qualificacao_imobiliaria(replace(base, creci_pj_regiao="CRECI/SP"))
        assert "nº 00001-J (CRECI/SP), neste ato" in so_pj
        assert "CRECI 000002-F, endereço" in so_pj
        so_resp = frases.qualificacao_imobiliaria(replace(base, responsavel_creci_regiao="2ª Região"))
        assert "nº 00001-J, neste ato" in so_resp
        assert "CRECI 000002-F (2ª Região), endereço" in so_resp


class TestSelecao:
    def test_no_resolved_company_is_a_named_gap(self):
        d = fx.variante(1)
        d = replace(d, imobiliaria=replace(d.imobiliaria, id=None))
        campos = [f["campo"] for f in _avaliar(d).faltando]
        assert "imobiliaria.selecao" in campos

    def test_a_resolved_company_has_no_selecao_gap(self):
        campos = [f["campo"] for f in _avaliar(fx.variante(1)).faltando]
        assert "imobiliaria.selecao" not in campos


class TestAvisoCorretagem:
    CODIGO = "CORRETAGEM_FAVORECIDO_DIFERENTE_DA_IMOBILIARIA"

    def _com_favorecido(self, cpf_cnpj: str | None):
        d = fx.variante(1)
        fav = Favorecido(id="fav-org", nome="Outra Pessoa", cpf_cnpj=cpf_cnpj)
        return replace(d, favorecidos=[fav] + [f for f in d.favorecidos if f.id != "fav-org"])

    def test_a_different_payee_warns_without_blocking(self):
        av = _avaliar(self._com_favorecido("529.982.247-25"))
        assert self.CODIGO in [a["codigo"] for a in av.avisos]
        assert self.CODIGO not in [b["codigo"] for b in av.bloqueios]

    def test_the_same_cnpj_does_not_warn(self):
        av = _avaliar(self._com_favorecido("11.222.333/0001-81"))
        assert self.CODIGO not in [a["codigo"] for a in av.avisos]

    def test_a_payee_without_a_document_does_not_warn(self):
        av = _avaliar(self._com_favorecido(None))
        assert self.CODIGO not in [a["codigo"] for a in av.avisos]
