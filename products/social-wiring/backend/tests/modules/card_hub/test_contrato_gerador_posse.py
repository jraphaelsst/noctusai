"""The posse clause's TIMING shapes the office's signed contracts use — each
pinned by its READINESS rule and by a RENDER (wording + lint clean):

- a prazo of N days from the marco (the long-standing shape);
- prazo 0 = CONCOMITANT with the marco ("concomitante com o recebimento da
  Parcela 04"; "na apresentação do protocolo de entrada do Registro de
  Imóveis ..."). 0 is an ANSWER, never "missing", and never prints "0 dias";
- a FIXED calendar date ("na data de 30 de novembro de 2026"), conditioned
  on the price being paid in full (migration 201, marco `data_fixa`).

All data synthetic (`contrato_gerador_fixtures`).
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest
from noctusai_lib.integrations.docx_render import get_docx_render_adapter

from app.modules.card_hub.contrato_gerador import derivacao, documento, frases, lint
from tests.modules.card_hub import contrato_gerador_fixtures as fx


def _avaliar(d, n: int):
    pol = fx.politica_variante(n)
    sw = derivacao.derivar_switches(d, pol, fx.REFERENCIA)
    return derivacao.avaliar(d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)


def _campos(av) -> list[str]:
    return [f["campo"] for f in av.faltando]


def _texto(d, n: int) -> str:
    pol = fx.politica_variante(n)
    sw = derivacao.derivar_switches(d, pol, fx.REFERENCIA)
    av = derivacao.avaliar(d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)
    assert av.pronto, (av.faltando, av.bloqueios)
    r = documento.renderizar(get_docx_render_adapter(real=True), d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)
    assert lint.lint(r.paragrafos, referencias=r.referencias, clausulas=r.clausulas) == []
    return "\n".join(r.paragrafos)


def _com_termos(n: int, **campos):
    d = fx.variante(n)
    return replace(d, termos=replace(d.termos, **campos))


class TestPrazoZeroEConcomitante:
    def test_zero_is_not_reported_missing(self):
        av = _avaliar(_com_termos(1, posse_prazo_dias=0), 1)
        assert "negociacao.posse_prazo_dias" not in _campos(av)

    def test_none_is_still_missing(self):
        av = _avaliar(_com_termos(1, posse_prazo_dias=None), 1)
        assert "negociacao.posse_prazo_dias" in _campos(av)

    def test_zero_on_a_parcela_marco_prints_concomitante_never_zero_dias(self):
        texto = _texto(_com_termos(1, posse_prazo_dias=0, posse_marco="parcela"), 1)
        assert "concomitante com o recebimento da parcela " in texto
        assert "0 (zero)" not in texto

    def test_zero_on_the_signing_marco(self):
        texto = _texto(
            _com_termos(1, posse_prazo_dias=0, posse_marco="assinatura", posse_marco_parcela_id=None), 1
        )
        assert "concomitante com a assinatura do presente contrato" in texto
        assert "0 (zero)" not in texto

    def test_zero_on_the_registry_protocol_marco(self):
        texto = _texto(
            _com_termos(1, posse_prazo_dias=0, posse_marco="protocolo_registro", posse_marco_parcela_id=None), 1
        )
        assert "na apresentação do protocolo de entrada do registro de imóveis e pagamento da guia de ITBI" in texto
        assert "0 (zero)" not in texto

    def test_a_positive_prazo_keeps_its_wording(self):
        texto = _texto(_com_termos(1, posse_prazo_dias=30, posse_marco="assinatura", posse_marco_parcela_id=None), 1)
        assert "em até 30 (trinta) dias corridos a contar da assinatura do presente contrato" in texto
        assert "concomitante" not in texto

    def test_the_permuta_posse_accepts_zero_too(self):
        d = _com_termos(5, permuta_posse_prazo_dias=0, permuta_posse_marco="assinatura")
        av = _avaliar(d, 5)
        assert "negociacao.permuta_posse_prazo_dias" not in _campos(av)
        texto = _texto(d, 5)
        assert "concomitante com a assinatura do presente contrato" in texto
        assert "0 (zero)" not in texto

    def test_permuta_positive_prazo_wording_is_unchanged(self):
        texto = _texto(_com_termos(5, permuta_posse_prazo_dias=60, permuta_posse_marco="assinatura"), 5)
        assert "no prazo máximo de 60 (sessenta) dias corridos a contar da assinatura do presente contrato." in texto


class TestPosseEmDataFixa:
    DATA = date(2026, 11, 30)

    def _d(self, **extra):
        return _com_termos(
            1, posse_marco="data_fixa", posse_data=self.DATA, posse_prazo_dias=None,
            posse_marco_parcela_id=None, **extra,
        )

    def test_it_is_ready_without_a_prazo(self):
        av = _avaliar(self._d(), 1)
        assert _campos(av) == []
        assert av.bloqueios == []

    def test_the_date_is_required(self):
        av = _avaliar(replace(self._d(), termos=replace(self._d().termos, posse_data=None)), 1)
        assert "negociacao.posse_data" in _campos(av)
        assert "negociacao.posse_prazo_dias" not in _campos(av)

    def test_the_missing_date_lands_on_the_posse_controls(self):
        av = _avaliar(replace(self._d(), termos=replace(self._d().termos, posse_data=None)), 1)
        item = next(f for f in av.faltando if f["campo"] == "negociacao.posse_data")
        assert item["destino"]["alvo"] == derivacao.ALVO_POSSE

    def test_it_renders_the_date_and_the_full_payment_condition(self):
        texto = _texto(self._d(), 1)
        assert "na data de 30 de novembro de 2026, com a condição que todas as parcelas do preço" in texto
        posse = texto.split("a posse do imóvel objeto deste contrato", 1)[1].split("\n", 1)[0]
        assert "dias" not in posse

    def test_the_permuta_posse_cannot_be_a_fixed_date(self):
        d = _com_termos(5, permuta_posse_marco="data_fixa", permuta_posse_prazo_dias=3)
        assert "POSSE_MARCO_INVALIDO" in [b["codigo"] for b in _avaliar(d, 5).bloqueios]


class TestFrases:
    def test_a_fixed_date_without_the_date_is_refused_loudly(self):
        with pytest.raises(ValueError):
            frases.posse_prazo_texto(None, "data_fixa", ref_parcela="")

    def test_a_missing_prazo_is_refused_loudly(self):
        with pytest.raises(ValueError):
            frases.posse_prazo_texto(None, "assinatura", ref_parcela="")
