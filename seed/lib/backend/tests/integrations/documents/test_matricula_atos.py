"""`segment_matricula_atos` — acts of a matrícula as literal OFFSETS.

🔴 WHAT THESE ARE FOR
---------------------
The contract quotes the matrícula literally (typos included) and the operator
selects spans. So the load-bearing properties are the invariants — spans are
contiguous, cover every character, and slice back byte-identical — checked over
EVERY fixture below. The per-fixture tests pin which headers split and, just as
important, which look-alikes must NOT split.

All names, numbers and addresses are invented.
"""
from __future__ import annotations

import dataclasses

import pytest

from noctusai_lib.integrations.documents import (
    MatriculaAto,
    ato_hint_span,
    segment_matricula_atos,
)

PADRAO = (
    "CARTORIO DE REGISTRO DE IMOVEIS FICTICIO\n"
    "MATRICULA Nº 12.345 - LIVRO 2 - FICHA 01\n"
    "IMOVEL: Lote 7 da Quadra B, Rua das Acacias Inventadas, 100.\n"
    "PROPRIETARIO: FULANO DE TESTE.\n"
    "R-1/12.345 - Em 10 de marco de 2001. VENDA. Transmitente: FULANO DE TESTE;\n"
    "adquirente: BELTRANA EXEMPLO. Valor R$ 150.000,00. O Oficial.\n"
    "AV-2/12.345 - Em 05 de abril de 2002. CONSTRUCAO averbada.\n"
    "R-3/12.345 - Em 01 de junho de 2003. HIPOTECA a favor do BANCO FICTICIO.\n"
)

VARIANTES = (
    "Matricula 9.876\nAbertura com descricao do imovel.\n"
    "R.1 - Em 02/02/2010, compra e venda.\n"
    "Av.2 - Averbacao de casamento.\n"
    "R 03 - Alienacao fiduciaria.\n"
    "AV . 4: cancelamento.\n"
    "AV.05/9.876 - Averbacao de numero de contribuinte.\n"
    "R.6-9.876 - Doacao.\n"
)

PAGINAS_E_MEIO_DE_LINHA = (
    "MATRICULA 555\nTerreno urbano ficticio.\n"
    "R-1/555 - Em 2015 venda a CICRANO FALSO. Dou fe. O Oficial.\n"
    "\n"
    "AV-2/555 - Em 2016 construcao. Dou fe. R-3/555 - Em 2017 venda a outro.\n"
    "Dou fe.\n\n"
    "   AV-4/555 - Em 2018 cancelamento do R-3, conforme R-3 e AV-2 acima.\n"
)

MINUSCULAS_E_ACENTOS = (
    "matrícula nº 321\n"
    "descrição: apartamento fictício nº 12, avenida 1, quadra r-1 do loteamento.\n"
    "av-1 – averbação de área.\n"
    "r.2 — venda à pessoa inventada.\n"
    "Av.3/321: retificação.\n"
)

DECOYS = (
    "MATRICULA 4.444\n"
    "Rua R 12, lote 3; valor R$ 1.000,00 e AVENIDA 2.\n"
    "Quadra R-1 do loteamento, conforme R-9 da matricula anterior.\n"
    "R-12345 nao e cabecalho.\n"
    "R-1,5 metros de frente.\n"
    "R-1 - Em 2020 venda.\n"
    "R-1 citado de novo nao abre ato.\n"
    "AV-2X nao e cabecalho.\n"
)

COMECA_COM_ATO = "R-1/77 - venda.\nAV-2/77 - averbacao.\n"

SO_ABERTURA = "MATRICULA 88\nApenas a abertura, sem atos.\n"

CRLF_NBSP_COMBINANTES = (
    "Matrícula 66\r\n"
    "Descrição com ligadura ﬁcticia.\r\n"
    "R - 1/66 - venda.\r\n"
    "\r\n"
    "AV-2/66 - fim.́\r\n"
)

ESPACO_EM_BRANCO = "\n\n   \n"

FIXTURES = {
    "padrao": PADRAO,
    "variantes": VARIANTES,
    "paginas_e_meio_de_linha": PAGINAS_E_MEIO_DE_LINHA,
    "minusculas_e_acentos": MINUSCULAS_E_ACENTOS,
    "decoys": DECOYS,
    "comeca_com_ato": COMECA_COM_ATO,
    "so_abertura": SO_ABERTURA,
    "crlf_nbsp_combinantes": CRLF_NBSP_COMBINANTES,
    "espaco_em_branco": ESPACO_EM_BRANCO,
}


def _kinds(text: str) -> list[tuple[str, int | None]]:
    return [(a.kind, a.numero) for a in segment_matricula_atos(text)]


class TestInvariants:
    @pytest.mark.parametrize("nome", sorted(FIXTURES))
    def test_spans_are_contiguous_and_cover_everything(self, nome):
        text = FIXTURES[nome]
        atos = segment_matricula_atos(text)
        assert atos, nome
        assert atos[0].start == 0
        assert atos[-1].end == len(text)
        for anterior, proximo in zip(atos, atos[1:]):
            assert anterior.end == proximo.start
        for ato in atos:
            assert ato.start < ato.end

    @pytest.mark.parametrize("nome", sorted(FIXTURES))
    def test_slices_round_trip_byte_identical(self, nome):
        text = FIXTURES[nome]
        atos = segment_matricula_atos(text)
        assert "".join(a.quote(text) for a in atos) == text
        assert b"".join(
            text[a.start : a.end].encode("utf-8") for a in atos
        ) == text.encode("utf-8")

    @pytest.mark.parametrize("nome", sorted(FIXTURES))
    def test_headers_sit_inside_their_act_and_hints_inside_the_span(self, nome):
        text = FIXTURES[nome]
        for ato in segment_matricula_atos(text):
            if ato.kind == "abertura":
                assert ato.header_start is None and ato.header_end is None
                assert ato.numero is None
            else:
                assert ato.header_start == ato.start
                assert ato.start < ato.header_end <= ato.end
            ini, fim = ato_hint_span(text, ato)
            assert ato.start <= ini <= fim <= ato.end

    @pytest.mark.parametrize("nome", sorted(FIXTURES))
    def test_order_is_document_order(self, nome):
        atos = segment_matricula_atos(FIXTURES[nome])
        assert [a.start for a in atos] == sorted(a.start for a in atos)

    def test_empty_input_has_no_acts(self):
        assert segment_matricula_atos("") == []

    def test_records_are_immutable(self):
        ato = segment_matricula_atos(PADRAO)[1]
        assert isinstance(ato, MatriculaAto)
        with pytest.raises(dataclasses.FrozenInstanceError):
            ato.start = 0  # type: ignore[misc]


class TestRecognisedHeaders:
    def test_the_plain_case(self):
        assert _kinds(PADRAO) == [("abertura", None), ("R", 1), ("AV", 2), ("R", 3)]
        atos = segment_matricula_atos(PADRAO)
        assert PADRAO[atos[1].header_start : atos[1].header_end] == "R-1/12.345"
        assert atos[1].quote(PADRAO).startswith("R-1/12.345 - Em 10 de marco")
        assert atos[1].quote(PADRAO).endswith("O Oficial.\n")

    def test_the_abertura_is_everything_before_the_first_act(self):
        atos = segment_matricula_atos(PADRAO)
        assert atos[0].quote(PADRAO) == PADRAO[: PADRAO.index("R-1/")]

    def test_separator_spacing_and_padding_variants(self):
        assert _kinds(VARIANTES) == [
            ("abertura", None),
            ("R", 1),
            ("AV", 2),
            ("R", 3),
            ("AV", 4),
            ("AV", 5),
            ("R", 6),
        ]
        atos = segment_matricula_atos(VARIANTES)
        cabecalhos = [VARIANTES[a.header_start : a.header_end] for a in atos[1:]]
        assert cabecalhos == ["R.1", "Av.2", "R 03", "AV . 4", "AV.05/9.876", "R.6-9.876"]

    def test_page_joins_and_mid_line_headers_after_a_sentence(self):
        assert _kinds(PAGINAS_E_MEIO_DE_LINHA) == [
            ("abertura", None),
            ("R", 1),
            ("AV", 2),
            ("R", 3),
            ("AV", 4),
        ]
        atos = segment_matricula_atos(PAGINAS_E_MEIO_DE_LINHA)
        # The page-join blank line stays at the tail of the previous act.
        assert atos[1].quote(PAGINAS_E_MEIO_DE_LINHA).endswith("O Oficial.\n\n")
        assert atos[3].quote(PAGINAS_E_MEIO_DE_LINHA).startswith("R-3/555 - Em 2017")
        # Indentation before a line-start header stays with the previous act.
        assert atos[3].quote(PAGINAS_E_MEIO_DE_LINHA).endswith("Dou fe.\n\n   ")

    def test_lowercase_and_accents_match_but_are_never_rewritten(self):
        assert _kinds(MINUSCULAS_E_ACENTOS) == [
            ("abertura", None),
            ("AV", 1),
            ("R", 2),
            ("AV", 3),
        ]
        atos = segment_matricula_atos(MINUSCULAS_E_ACENTOS)
        assert atos[1].quote(MINUSCULAS_E_ACENTOS) == "av-1 – averbação de área.\n"
        assert atos[2].quote(MINUSCULAS_E_ACENTOS) == "r.2 — venda à pessoa inventada.\n"

    def test_an_act_at_offset_zero_has_no_abertura(self):
        assert _kinds(COMECA_COM_ATO) == [("R", 1), ("AV", 2)]

    def test_offsets_survive_crlf_nbsp_ligatures_and_combining_marks(self):
        text = CRLF_NBSP_COMBINANTES
        atos = segment_matricula_atos(text)
        assert [(a.kind, a.numero) for a in atos] == [("abertura", None), ("R", 1), ("AV", 2)]
        assert text[atos[1].header_start : atos[1].header_end] == "R - 1/66"
        assert atos[2].quote(text) == "AV-2/66 - fim.́\r\n"


class TestNeverSplits:
    def test_look_alikes_and_citations_stay_inside_the_previous_span(self):
        assert _kinds(DECOYS) == [("abertura", None), ("R", 1)]
        atos = segment_matricula_atos(DECOYS)
        assert atos[0].quote(DECOYS).endswith("R-1,5 metros de frente.\n")
        # A repeated (kind, numero) is a citation, kept inside R-1; a header
        # glued to a letter (`AV-2X`) is not a header.
        assert atos[1].quote(DECOYS).endswith("R-1 citado de novo nao abre ato.\nAV-2X nao e cabecalho.\n")

    def test_a_date_after_the_dash_is_not_a_matricula_suffix(self):
        text = "MATRICULA 5\nR-1 - 2020 venda.\n"
        atos = segment_matricula_atos(text)
        assert text[atos[1].header_start : atos[1].header_end] == "R-1"

    def test_body_citations_after_a_word_do_not_split(self):
        atos = segment_matricula_atos(PAGINAS_E_MEIO_DE_LINHA)
        assert "cancelamento do R-3, conforme R-3 e AV-2" in atos[-1].quote(
            PAGINAS_E_MEIO_DE_LINHA
        )

    def test_mid_line_header_without_separator_does_not_split(self):
        text = "MATRICULA 1\nAbertura. R-1 venda sem separador.\n"
        assert _kinds(text) == [("abertura", None)]

    def test_no_acts_is_a_single_abertura(self):
        assert _kinds(SO_ABERTURA) == [("abertura", None)]
        assert _kinds(ESPACO_EM_BRANCO) == [("abertura", None)]


class TestHintSpan:
    def test_first_line_trimmed(self):
        atos = segment_matricula_atos(PADRAO)
        ini, fim = ato_hint_span(PADRAO, atos[2])
        assert PADRAO[ini:fim] == "AV-2/12.345 - Em 05 de abril de 2002. CONSTRUCAO averbada."

    def test_abertura_hint_skips_leading_blank_lines(self):
        text = "\n\n  MATRICULA 10  \nresto\nR-1 - venda.\n"
        atos = segment_matricula_atos(text)
        ini, fim = ato_hint_span(text, atos[0])
        assert text[ini:fim] == "MATRICULA 10"

    def test_mid_line_act_hint_is_the_rest_of_that_line(self):
        atos = segment_matricula_atos(PAGINAS_E_MEIO_DE_LINHA)
        ini, fim = ato_hint_span(PAGINAS_E_MEIO_DE_LINHA, atos[3])
        assert PAGINAS_E_MEIO_DE_LINHA[ini:fim] == "R-3/555 - Em 2017 venda a outro."

    def test_crlf_is_not_part_of_the_hint(self):
        atos = segment_matricula_atos(CRLF_NBSP_COMBINANTES)
        ini, fim = ato_hint_span(CRLF_NBSP_COMBINANTES, atos[1])
        assert CRLF_NBSP_COMBINANTES[ini:fim] == "R - 1/66 - venda."

    def test_all_blank_span_hint_is_empty(self):
        atos = segment_matricula_atos(ESPACO_EM_BRANCO)
        assert ato_hint_span(ESPACO_EM_BRANCO, atos[0]) == (0, 0)
