"""`caixa_rotulada` — the shared labelled-box matcher `cartao_cnpj.py`,
`financiamento_imobiliario.py` and `guia_itbi.py` all migrated onto
(883, 2026-09-27/28). These tests exercise the PRIMITIVES directly with
small, synthetic label vocabularies — the drift each mechanism fixes is
ALSO exercised through the real document readers' own tests
(`test_financiamento_imobiliario.py`'s `TestItauQuadro`, `data_documento`
ordering and `valor_fgts` synonym tests in particular); these ones isolate
each mechanism on its own so a future regression here fails close to the
actual bug, not three files away."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from noctusai_lib.integrations.documents.caixa_rotulada import (
    campo,
    data_br,
    embutido_em_rotulo_maior,
    percentual,
    pessoas_com_cpf,
    proxima_ocorrencia,
    resolver_valor_caixa,
    temperar_alta_por_fonte,
)
from noctusai_lib.integrations.documents.types import ExtractionConfidence, TextSource

CPF_VALIDO = "412.954.238-98"
CPF_INVALIDO = "412.954.238-99"


class TestOtherFieldLongerLabelGuard:
    """A label that is a genuine SUBSTRING of a LONGER label belonging to a
    DIFFERENT field is not this field's box (883, Itaú: "PRECO DE VENDA DO
    IMOVEL" sits inside "VALOR DESTINADO AO PAGAMENTO DO PRECO DE VENDA DO
    IMOVEL") — the guard `financiamento_imobiliario` alone used to carry;
    `guia_itbi` had none at all."""

    def test_embedded_occurrence_is_rejected_for_the_shorter_field(self):
        linhas = ["VALOR DESTINADO AO PAGAMENTO DO PRECO DE VENDA DO IMOVEL: R$ 400.000,00"]
        todos = (
            "PRECO DE VENDA DO IMOVEL",
            "VALOR DESTINADO AO PAGAMENTO DO PRECO DE VENDA DO IMOVEL",
        )
        valor, achado, mascarado = campo(
            linhas,
            ("PRECO DE VENDA DO IMOVEL",),
            todos_rotulos=todos,
        )
        assert (valor, achado, mascarado) == (None, None, False)

    def test_the_longer_labels_own_field_still_reads_it(self):
        linhas = ["VALOR DESTINADO AO PAGAMENTO DO PRECO DE VENDA DO IMOVEL: R$ 400.000,00"]
        todos = (
            "PRECO DE VENDA DO IMOVEL",
            "VALOR DESTINADO AO PAGAMENTO DO PRECO DE VENDA DO IMOVEL",
        )
        valor, achado, mascarado = campo(
            linhas,
            ("VALOR DESTINADO AO PAGAMENTO DO PRECO DE VENDA DO IMOVEL",),
            todos_rotulos=todos,
        )
        assert valor == "R$ 400.000,00"
        assert achado == "VALOR DESTINADO AO PAGAMENTO DO PRECO DE VENDA DO IMOVEL"
        assert mascarado is False

    def test_a_genuinely_separate_occurrence_of_the_shorter_label_still_reads(self):
        """The guard only rejects an occurrence that is ACTUALLY embedded —
        a separate, standalone occurrence of the shorter label elsewhere is
        still admissible."""
        linhas = [
            "VALOR DESTINADO AO PAGAMENTO DO PRECO DE VENDA DO IMOVEL: R$ 400.000,00",
            "1 - PRECO DE VENDA DO IMOVEL: R$ 500.000,00",
        ]
        todos = (
            "PRECO DE VENDA DO IMOVEL",
            "VALOR DESTINADO AO PAGAMENTO DO PRECO DE VENDA DO IMOVEL",
        )
        valor, achado, mascarado = campo(
            linhas,
            ("PRECO DE VENDA DO IMOVEL",),
            todos_rotulos=todos,
        )
        assert valor == "R$ 500.000,00"
        assert achado == "PRECO DE VENDA DO IMOVEL"

    def test_embutido_em_rotulo_maior_directly(self):
        linha = "VALOR DESTINADO AO PAGAMENTO DO PRECO DE VENDA DO IMOVEL: R$ 400.000,00"
        pos = linha.find("PRECO DE VENDA DO IMOVEL")
        assert embutido_em_rotulo_maior(
            linha, pos, "PRECO DE VENDA DO IMOVEL",
            ("VALOR DESTINADO AO PAGAMENTO DO PRECO DE VENDA DO IMOVEL",),
        ) is True


class TestEveryOccurrencePerLine:
    """`financiamento_imobiliario`'s original `_campo` used a bare
    `linha.find(rotulo)` — only the FIRST occurrence on a line was ever
    considered, so a guarded first occurrence made the whole line a dead
    end even when a second, genuinely admissible, occurrence sat later on
    the SAME line."""

    def test_a_guarded_first_occurrence_does_not_starve_a_later_admissible_one(self):
        linha = (
            "VALOR DESTINADO AO PAGAMENTO DO PRECO DE VENDA DO IMOVEL: R$ 400.000,00 "
            "-- 1 - PRECO DE VENDA DO IMOVEL: R$ 500.000,00"
        )
        todos = (
            "PRECO DE VENDA DO IMOVEL",
            "VALOR DESTINADO AO PAGAMENTO DO PRECO DE VENDA DO IMOVEL",
        )
        valor, achado, mascarado = campo(
            [linha],
            ("PRECO DE VENDA DO IMOVEL",),
            todos_rotulos=todos,
        )
        assert valor == "R$ 500.000,00"
        assert achado == "PRECO DE VENDA DO IMOVEL"


class TestLongestSynonymFirst:
    """Synonyms are tried longest-first, NEVER in `sinonimos`'s own
    declared order — a bare label can no longer shadow a more specific one
    just because a caller happened to declare it first
    (`financiamento_imobiliario.data_documento` listed bare "DATA" first;
    `prazo_meses`'s bare "PRAZO" needed the identical hand-fix once)."""

    def test_a_bare_synonym_declared_first_never_wins_over_a_specific_one(self):
        linha = "FOO BAR BAZ: 42"
        valor, achado, _ = campo(
            [linha], ("FOO", "FOO BAR BAZ"), todos_rotulos=("FOO", "FOO BAR BAZ")
        )
        assert achado == "FOO BAR BAZ"
        assert valor == "42"

    def test_ties_in_length_preserve_declared_order(self):
        """`sorted(..., key=len, reverse=True)` is a STABLE sort — when two
        synonyms tie in length, whichever is declared first is tried
        first."""
        linha = "AA: 1 BB: 2"
        valor, achado, _ = campo([linha], ("AA", "BB"), todos_rotulos=("AA", "BB"))
        assert (achado, valor) == ("AA", "1")

        valor2, achado2, _ = campo([linha], ("BB", "AA"), todos_rotulos=("AA", "BB"))
        assert (achado2, valor2) == ("BB", "2")


class TestWordBoundaryMatching:
    """A bare label like "BANCO" must never match INSIDE a longer word
    ("UNIBANCO") — neither when locating the field's own label, nor when
    computing where to CUT a value off at "the next known label"."""

    def test_a_bare_label_does_not_match_inside_a_longer_word(self):
        linha = "ITAU UNIBANCO S.A."
        assert proxima_ocorrencia(linha, 0, "BANCO", ("BANCO",)) is None

    def test_a_bare_label_still_matches_as_its_own_standalone_word(self):
        linha = "0341 BANCO ITAU"
        assert proxima_ocorrencia(linha, 0, "BANCO", ("BANCO",)) == 5

    def test_the_cutoff_search_does_not_truncate_at_a_label_embedded_in_a_word(self):
        """The exact 883 drift: "CREDOR: ITAÚ UNIBANCO" used to cut the
        bank name at the "BANCO" sitting inside "UNIBANCO"."""
        linha = "CREDOR ITAU UNIBANCO S.A."
        valor, mascarado = resolver_valor_caixa(
            [linha], 0, linha, 0, "CREDOR", ("CREDOR", "BANCO")
        )
        assert valor == "ITAU UNIBANCO S.A."
        assert mascarado is False

    def test_the_cutoff_search_still_truncates_at_a_genuine_standalone_label(self):
        linha = "CREDOR ITAU BANCO XPTO"
        valor, _mascarado = resolver_valor_caixa(
            [linha], 0, linha, 0, "CREDOR", ("CREDOR", "BANCO")
        )
        assert valor == "ITAU"


class TestTituloDocumentoGuard:
    """Opt-in: a document family with no title hazard (`financiamento_imobiliario`,
    `guia_itbi`) simply never passes `titulo_documento`, and the guard is a
    permanent no-op for them."""

    def test_no_titulo_documento_never_rejects_anything(self):
        linha = "SITUACAO CADASTRAL: ATIVA"
        idx = proxima_ocorrencia(linha, 0, "SITUACAO CADASTRAL", ("SITUACAO CADASTRAL",))
        assert idx == 0

    def test_an_occurrence_inside_the_title_is_rejected(self):
        titulo = "COMPROVANTE DE INSCRICAO E DE SITUACAO CADASTRAL"
        idx = proxima_ocorrencia(
            titulo, 0, "SITUACAO CADASTRAL", ("SITUACAO CADASTRAL",), titulo_documento=titulo
        )
        assert idx is None

    def test_a_real_box_further_down_is_still_reached(self):
        linhas = [
            "COMPROVANTE DE INSCRICAO E DE SITUACAO CADASTRAL",
            "SITUACAO CADASTRAL: ATIVA",
        ]
        valor, achado, _ = campo(
            linhas,
            ("SITUACAO CADASTRAL",),
            todos_rotulos=("SITUACAO CADASTRAL",),
            titulo_documento="COMPROVANTE DE INSCRICAO E DE SITUACAO CADASTRAL",
        )
        assert valor == "ATIVA"
        assert achado == "SITUACAO CADASTRAL"


class TestValoresMascarados:
    def test_an_exact_masked_token_is_mascarado_true_valor_none(self):
        linha = "TITULO: ********"
        valor, achado, mascarado = campo(
            [linha], ("TITULO",), todos_rotulos=("TITULO",), valores_mascarados=("********",)
        )
        assert (valor, achado, mascarado) == (None, "TITULO", True)

    def test_no_valores_mascarados_declared_never_masks_anything(self):
        linha = "TITULO: ********"
        valor, _achado, mascarado = campo([linha], ("TITULO",), todos_rotulos=("TITULO",))
        assert valor == "********"
        assert mascarado is False

    def test_masked_on_the_next_line_is_also_recognised(self):
        linhas = ["TITULO:", "[EM BRANCO]"]
        valor, _achado, mascarado = campo(
            linhas, ("TITULO",), todos_rotulos=("TITULO",), valores_mascarados=("[EM BRANCO]",)
        )
        assert (valor, mascarado) == (None, True)


class TestNoAdmissibleOccurrenceAtAll:
    def test_a_label_never_printed_returns_the_all_none_triple(self):
        assert campo(["ALGO IRRELEVANTE"], ("TITULO",), todos_rotulos=("TITULO",)) == (
            None,
            None,
            False,
        )


class TestSharedSmallParsers:
    """`_temper`/`_data_br`/`_percentual`/`_pessoas` had ALSO drifted into
    2-3 identical copies across the same three files — folded in here
    because their semantics were byte-identical."""

    def test_temperar_alta_por_fonte_caps_alta_off_text_layer(self):
        assert (
            temperar_alta_por_fonte(ExtractionConfidence.ALTA, TextSource.OCR)
            is ExtractionConfidence.BAIXA
        )
        assert (
            temperar_alta_por_fonte(ExtractionConfidence.ALTA, TextSource.TEXT_LAYER)
            is ExtractionConfidence.ALTA
        )
        assert (
            temperar_alta_por_fonte(ExtractionConfidence.MEDIA, TextSource.OCR)
            is ExtractionConfidence.MEDIA
        )

    def test_data_br_parses_ddmmyyyy_anywhere_in_the_text(self):
        assert data_br("Emitido em 15/03/2020 as 10h") == date(2020, 3, 15)

    def test_data_br_none_for_blank_or_unparseable(self):
        assert data_br(None) is None
        assert data_br("") is None
        assert data_br("sem data nenhuma aqui") is None

    def test_data_br_none_for_an_impossible_date(self):
        assert data_br("31/02/2020") is None

    def test_percentual_parses_comma_decimal(self):
        assert percentual("Taxa: 9,5%") == Decimal("9.5")

    def test_percentual_none_for_blank_or_unparseable(self):
        assert percentual(None) is None
        assert percentual("sem percentual") is None

    def test_pessoas_com_cpf_uses_the_callers_own_factory(self):
        criados: list[tuple] = []

        def fabrica(nome, cpf, cpf_valido):
            criados.append((nome, cpf, cpf_valido))
            return (nome, cpf, cpf_valido)

        resultado = pessoas_com_cpf(
            f"Fulano de Tal - CPF: {CPF_VALIDO}; Ciclano - CPF: {CPF_INVALIDO}", fabrica
        )
        assert len(resultado) == 2
        assert resultado[0] == ("Fulano de Tal", CPF_VALIDO, True)
        assert resultado[1] == ("Ciclano", CPF_INVALIDO, False)
        assert criados == list(resultado)

    def test_pessoas_com_cpf_empty_for_blank_input(self):
        assert pessoas_com_cpf(None, lambda *a: a) == ()
        assert pessoas_com_cpf("", lambda *a: a) == ()

    def test_pessoas_com_cpf_drops_an_unformattable_cpf_entry(self):
        resultado = pessoas_com_cpf("Fulano - CPF: 123", lambda *a: a)
        assert resultado == ()


def test_pessoas_com_cpf_reads_every_pair_joined_by_e() -> None:
    from noctusai_lib.integrations.documents.caixa_rotulada import pessoas_com_cpf

    pessoas = pessoas_com_cpf(
        "FULANO SINTETICO - CPF: 412.954.238-98 E BELTRANA SINTETICA - CPF: 529.982.247-25.",
        lambda nome, cpf, ok: (nome, cpf, ok),
    )
    assert pessoas == (
        ("FULANO SINTETICO", "412.954.238-98", True),
        ("BELTRANA SINTETICA", "529.982.247-25", True),
    )
