"""F5 generator hardening — "a generated contract must never be silently wrong"
(owner goal, 2026-10-03). Pure, over the synthetic fixtures (no DB).

WHAT THESE PIN — each one passed silently before:
- typed obligations with no clause (`obrigacoes_vendedor`,
  `permuta_obrigacoes_entrega`) REFUSE generation instead of an aviso while
  the text quietly stayed off the instrument;
- no silent loader defaults: a financing with no `situacao` is `faltando`
  (and a non-approved one is announced), an intermediário with no `tipo` is
  `faltando` (never read as "percentual"), a certidão's consulta kind is
  inferred from the document's digit count or named — never "cpf";
- an unknown regime de bens / certidão resultado / estado civil refuses at
  the gate instead of printing a raw enum or an empty label;
- no default gender: printing a person without one REFUSES (gate and template
  must agree); a legacy deal never prints antigos the gate skipped;
- the matrícula-136 fallback (whole selection quoted) reaches the operator
  as an aviso, not only a server log;
- the post-render lint catches leaked None/null, empty slots and bracketed
  placeholders;
- the office's fixed legal terms live as named constants in `politica.py`
  with the wording unchanged.

All data is synthetic.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from noctusai_lib.integrations.docx_render import get_docx_render_adapter

from app.modules.card_hub.contrato_gerador import (
    carregador,
    derivacao,
    documento,
    frases,
    lint,
    modelo_texto,
    politica,
)
from app.modules.card_hub.contrato_gerador.dados import Financiamento
from tests.modules.card_hub import contrato_gerador_fixtures as fx


def _avaliar(n: int, d=None):
    d = d if d is not None else fx.variante(n)
    pol = fx.politica_variante(n)
    sw = derivacao.derivar_switches(d, pol, fx.REFERENCIA)
    return derivacao.avaliar(d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)


def _render(n: int, d):
    pol = fx.politica_variante(n)
    sw = derivacao.derivar_switches(d, pol, fx.REFERENCIA)
    av = derivacao.avaliar(d, sw, pol, fx.ASSINATURA, fx.REFERENCIA)
    assert av.pronto, (av.faltando, av.bloqueios)
    return documento.renderizar(
        get_docx_render_adapter(real=True), d, sw, pol, fx.ASSINATURA, fx.REFERENCIA
    )


def _codigos(itens) -> list[str]:
    return [i["codigo"] for i in itens]


def _campos(av) -> list[str]:
    return [f["campo"] for f in av.faltando]


# ─── 1. typed obligations with no clause refuse ──────────────────────────


class TestObrigacoesSemRedacaoRecusam:
    @pytest.mark.parametrize("campo, codigo, n", [
        ("obrigacoes_vendedor", "OBRIGACOES_VENDEDOR_SEM_REDACAO", 1),
        ("permuta_obrigacoes_entrega", "PERMUTA_OBRIGACOES_SEM_REDACAO", 5),
    ])
    def test_typed_text_blocks_instead_of_silently_vanishing(self, campo, codigo, n):
        d = fx.variante(n)
        d = replace(d, termos=replace(d.termos, **{campo: "Entregar o imóvel pintado."}))
        av = _avaliar(n, d)
        assert codigo in _codigos(av.bloqueios)
        assert codigo not in _codigos(av.avisos)
        assert not av.pronto
        mensagem = next(b["mensagem"] for b in av.bloqueios if b["codigo"] == codigo)
        assert "Apague o campo" in mensagem and "aguarde a cláusula" in mensagem

    def test_blank_text_is_not_an_obligation(self):
        d = fx.variante(1)
        d = replace(d, termos=replace(d.termos, obrigacoes_vendedor="   "))
        assert _avaliar(1, d).pronto


# ─── 3. no silent loader defaults ────────────────────────────────────────


class TestFinanciamentoSemDefault:
    def test_the_dataclass_no_longer_invents_pendente(self):
        assert Financiamento(existe=True).situacao is None

    def test_a_financing_with_no_situacao_is_missing_it(self):
        d = replace(fx.variante(1), financiamento=Financiamento(existe=True, situacao=None))
        av = _avaliar(1, d)
        assert "financiamento.situacao" in _campos(av)
        assert not av.pronto

    def test_a_pending_financing_is_announced_but_generates(self):
        d = replace(fx.variante(1), financiamento=Financiamento(existe=True, situacao="pendente"))
        av = _avaliar(1, d)
        assert "FINANCIAMENTO_NAO_APROVADO" in _codigos(av.avisos)
        assert av.pronto, (av.faltando, av.bloqueios)

    def test_an_approved_financing_is_quiet(self):
        av = _avaliar(1)
        assert "FINANCIAMENTO_NAO_APROVADO" not in _codigos(av.avisos)

    def test_an_unknown_situacao_blocks(self):
        d = replace(fx.variante(1), financiamento=Financiamento(existe=True, situacao="em_analise"))
        assert "FINANCIAMENTO_SITUACAO_DESCONHECIDA" in _codigos(_avaliar(1, d).bloqueios)


class TestIntermediarioSemTipo:
    def _com_tipo(self, tipo):
        d = fx.variante(1)
        return replace(d, intermediarios=[replace(i, tipo=tipo) for i in d.intermediarios])

    def test_a_missing_tipo_is_missing_not_percentual(self):
        av = _avaliar(1, self._com_tipo(None))
        assert "negociacao.intermediario.int-1.tipo" in _campos(av)
        assert not av.pronto

    def test_an_unknown_tipo_blocks(self):
        av = _avaliar(1, self._com_tipo("comissao_cheia"))
        assert "INTERMEDIARIO_TIPO_DESCONHECIDO" in _codigos(av.bloqueios)


class TestConsultaTipoDocumentoInferido:
    def _linha(self, **extra):
        return {"tipo": "serasa", "resultado": "negativa", "numero": "X-1",
                "emitida_em": "2026-09-01", "validade_ate": "2026-12-01", **extra}

    @pytest.mark.parametrize("documento_consulta, esperado", [
        ("11.222.333/0001-81", "cnpj"),
        ("11222333000181", "cnpj"),
        ("123.456.789-09", "cpf"),
        ("12345678909", "cpf"),
        ("123", None),
        (None, None),
    ])
    def test_the_digit_count_decides_never_a_cpf_default(self, documento_consulta, esperado):
        c = carregador._certidao(self._linha(consulta_documento=documento_consulta))
        assert c.consulta_tipo_documento == esperado

    def test_a_stored_kind_wins(self):
        c = carregador._certidao(self._linha(consulta_tipo_documento="cnpj", consulta_documento="12345678909"))
        assert c.consulta_tipo_documento == "cnpj"

    def test_an_unknown_kind_is_named_by_the_gate(self):
        d = fx.variante(1)
        v = d.vendedores[0]
        certs = [replace(c, consulta_tipo_documento=None) if c.tipo == "serasa" else c for c in v.certidoes]
        av = _avaliar(1, replace(d, vendedores=[replace(v, certidoes=certs)]))
        assert ("certidao.serasa.consulta_tipo_documento", v.parte_id) in [
            (f["campo"], f["parte_id"]) for f in av.faltando
        ]


# ─── 4. unknown vocabulary refuses; no default gender ────────────────────


def _casal(regime: str):
    d = fx.variante(1)
    v1 = replace(d.vendedores[0], estado_civil="casado", regime_bens=regime,
                 conjuge_cliente_id="v2", data_casamento=date(1990, 5, 5))
    v2 = replace(fx.pessoa("v2", "vendedor", "conjuge", "Cicrana Amostra", "Feminino", "111222333", "55.555.555-5"),
                 estado_civil="casado", regime_bens=regime, conjuge_cliente_id="v1",
                 data_casamento=date(1990, 5, 5))
    return replace(d, vendedores=[v1, v2])


class TestVocabularioDesconhecidoRecusa:
    def test_an_unknown_regime_blocks_instead_of_printing_the_enum(self):
        av = _avaliar(1, _casal("regime_inventado"))
        assert "REGIME_BENS_SEM_REDACAO" in _codigos(av.bloqueios)

    def test_a_casado_without_a_regime_is_missing_it(self):
        av = _avaliar(1, _casal(None))
        assert "qualificacao.regime_bens" in _campos(av)

    def test_a_known_regime_still_prints_its_wording(self):
        texto = "\n".join(_render(1, _casal("comunhao_universal")).paragrafos)
        assert "casados no regime da comunhão universal de bens" in texto

    def test_the_phrase_refuses_an_unknown_regime(self):
        d = _casal("regime_inventado")
        with pytest.raises(KeyError):
            frases.qualificacao(d.vendedores, lei_6515_desde=date(1977, 12, 26))

    def test_an_unknown_estado_civil_blocks(self):
        d = fx.variante(1)
        d = replace(d, vendedores=[replace(d.vendedores[0], estado_civil="noivo")])
        assert "ESTADO_CIVIL_SEM_REDACAO" in _codigos(_avaliar(1, d).bloqueios)

    def test_an_unknown_certidao_resultado_blocks_instead_of_an_empty_label(self):
        d = fx.variante(1)
        v = d.vendedores[0]
        certs = [replace(c, resultado="inconclusiva") if c.tipo == "cnd_federal" else c for c in v.certidoes]
        av = _avaliar(1, replace(d, vendedores=[replace(v, certidoes=certs)]))
        assert "CERTIDAO_RESULTADO_DESCONHECIDO" in _codigos(av.bloqueios)

    def test_the_label_refuses_an_unknown_resultado(self):
        with pytest.raises(KeyError):
            frases.rotulo_certidao("cnd_federal", "inconclusiva")
        # `None` stays the deliberate un-qualified label.
        assert "  " not in frases.rotulo_certidao("cnd_federal", None)


class TestSemGeneroPadrao:
    def test_a_missing_name_is_missing(self):
        d = fx.variante(1)
        d = replace(d, vendedores=[replace(d.vendedores[0], nome=None)])
        assert "qualificacao.nome_oficial" in _campos(_avaliar(1, d))

    def test_qualifying_a_person_without_gender_refuses(self):
        p = replace(fx.vendedor(), genero=None)
        with pytest.raises(ValueError, match="gênero"):
            frases.qualificacao([p], lei_6515_desde=date(1977, 12, 26))

    def test_the_antigos_phrase_refuses_a_person_without_gender(self):
        with pytest.raises(ValueError, match="gênero"):
            frases.antigos_proprietarios_texto([replace(fx.antiga_proprietaria(), genero=None)])

    def test_a_legacy_deal_never_prints_antigos_the_gate_skipped(self):
        """`processo_legado` skips the antigos' gate ("não entram no
        contrato") — so a RECORDED antiga with no gender must not reach the
        template either (it used to print, defaulted to masculine)."""
        d = fx.variante(1)
        antiga = replace(fx.antiga_proprietaria(), genero=None)
        d = replace(
            d,
            processo_legado=True,
            vendedores=d.vendedores + [antiga],
            imovel=replace(d.imovel, ultima_transferencia_em=date(2021, 9, 15)),
        )
        texto = "\n".join(_render(1, d).paragrafos)
        assert "ANTIGA DONA EXEMPLO" not in texto.upper()
        assert "antig" not in texto.lower()


# ─── 5. the matrícula-136 fallback reaches the operator ──────────────────


class TestDescricaoImovelAusenteAvisa:
    def test_the_main_imovel_fallback_is_an_aviso(self):
        d = fx.variante(1)
        d = replace(d, matricula=replace(d.matricula, descricao_imovel_texto=None))
        assert "MATRICULA_SEM_DESCRICAO_IMOVEL" in _codigos(_avaliar(1, d).avisos)

    def test_a_descricao_block_is_quiet(self):
        d = fx.variante(1)
        d = replace(d, matricula=replace(d.matricula, descricao_imovel_texto="Um lote de terreno."))
        assert "MATRICULA_SEM_DESCRICAO_IMOVEL" not in _codigos(_avaliar(1, d).avisos)

    def test_the_permuta_fallback_is_an_aviso(self):
        d = fx.variante(5)
        d = replace(d, permuta_imoveis=[replace(i, descricao_imovel_texto=None) for i in d.permuta_imoveis])
        assert "MATRICULA_PERMUTA_SEM_DESCRICAO_IMOVEL" in _codigos(_avaliar(5, d).avisos)


# ─── 6. lint catches leaked values and empty slots ───────────────────────


class TestLintLacunas:
    def _hits(self, texto: str) -> list[str]:
        return _codigos(lint.lint([texto], referencias={}, clausulas={}))

    @pytest.mark.parametrize("texto", [
        "residente na Rua None, nº 10.",
        "inscrito no CPF/MF null.",
        "com endereço eletrônico: undefined.",
    ])
    def test_a_leaked_null_value_is_a_hit(self, texto):
        assert "VALOR_NULO_IMPRESSO" in self._hits(texto)

    @pytest.mark.parametrize("texto", [
        "Rua das Flores, , Bairro Centro.",
        "Rua das Flores, nº , Bairro Centro.",
        "Imóvel cadastrado sob nº .",
        "acrescido de juros ( ) ao mês.",
        "CPF: , RG 1.",
        "Bairro Centro  , Cidade.",
    ])
    def test_an_empty_slot_is_a_hit(self, texto):
        assert "LACUNA_NO_TEXTO" in self._hits(texto)

    @pytest.mark.parametrize("texto", ["emitida em [DATA AUSENTE].", "em favor de [NOME DO FAVORECIDO]."])
    def test_a_bracketed_placeholder_is_a_hit(self, texto):
        assert "PLACEHOLDER_NO_TEXTO" in self._hits(texto)

    @pytest.mark.parametrize("texto", [
        "Rua das Flores, nº 10 - Centro - Cidade/SP – CEP: 01000-000.",
        "a nulidade do contrato (art. 166) não se presume.",
        "conforme a matrícula [ilegível no original] do imóvel.",
        "FULANO DE TAL    fulano@exemplo.test",
    ])
    def test_ordinary_wording_is_clean(self, texto):
        assert self._hits(texto) == []


# ─── 7. the office's fixed legal terms are named constants ───────────────


class TestTermosFixosDoEscritorio:
    FRASES = (
        "multa moratória de 2% (dois por cento) sobre o valor da parcela em atraso;",
        "juros moratórios de 1% (um por cento) ao mês, calculados pro rata die;",
        "correção monetária pelo IGPM, ou por outro índice oficial",
        "O atraso superior a 30 (trinta) dias no pagamento de qualquer parcela, "
        "ou o inadimplemento de 02 (duas) parcelas,",
        "no prazo máximo de 30 dias após a posse",
        "no prazo máximo de 2 dias úteis após a rescisão do Contrato.",
        "com multa moratória de 2% (dois por cento) sobre o valor do débito, acrescido de "
        "juros moratórios de 1% (um por cento) ao mês e correção monetária pelo IGPM.",
    )

    def test_the_constants_are_the_office_standard(self):
        assert politica.MULTA_MORATORIA == "2% (dois por cento)"
        assert politica.JUROS_MORATORIOS_AM == "1% (um por cento)"
        assert politica.INDICE_CORRECAO_MONETARIA == "IGPM"
        assert politica.VENCIMENTO_ANTECIPADO_ATRASO == "30 (trinta) dias"
        assert politica.VENCIMENTO_ANTECIPADO_PARCELAS == "02 (duas) parcelas"
        assert politica.PRAZO_DEVOLUCAO_RESCISAO == "2 dias úteis"
        assert politica.PRAZO_ATUALIZACAO_CADASTROS == "30 dias"

    @pytest.mark.parametrize("frase", FRASES)
    def test_the_printed_wording_is_unchanged(self, frase):
        assert frase in modelo_texto.TEMPLATE

    def test_the_raw_wording_carries_no_literal_term(self):
        """The constants are the ONE source — no clause hard-codes a term."""
        for valor in modelo_texto.TERMOS_FIXOS.values():
            if valor == "IGPM":
                assert "IGPM" not in modelo_texto._TEMPLATE_BRUTO
            else:
                assert valor not in modelo_texto._TEMPLATE_BRUTO
        assert "⟪" not in modelo_texto.TEMPLATE

    def test_a_marker_without_a_constant_fails_loudly(self):
        with pytest.raises(RuntimeError):
            modelo_texto._aplicar_termos_fixos("multa de ⟪TERMO_INEXISTENTE⟫")
