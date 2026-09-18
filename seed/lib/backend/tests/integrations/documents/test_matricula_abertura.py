"""`segmentar_abertura` — typed blocks of a matrícula's abertura, as offsets.

🔴 WHAT THESE PIN
------------------
1. All four labels segmented, in document order, on a Provider-A-shaped
   abertura (real coverage: `IMÓVEL` 7/7, `CADASTRO` 7/7).
2. `descricao_imovel` never includes the `IMÓVEL:` label itself.
3. A missing `PROPRIETÁRIOS` (Provider-B shape, where it is folded into the
   imóvel paragraph with no label of its own — real coverage 4/7) yields NO
   block for that field, never a wrong one.
4. Accent/case/separator tolerance, and singular/plural for PROPRIETÁRIO(S).
5. A label NOT at the start of a line (prose merely using the word) is never
   mistaken for a block header.
6. THE REGRESSION FOUND AGAINST REAL DOCUMENTS: the last block stops before
   the abertura's closing locale+date and the officer's signature (`O
   Oficial,` / `O Oficial Substituto,`) instead of swallowing them.
7. No block's slice starts or ends with whitespace, on every fixture.
8. Every offset is a valid slice; `rotulo_start/end` sit inside `start`.

All names, numbers and addresses are invented.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents.matricula_abertura import (
    BlocoAbertura,
    segmentar_abertura,
)

# Provider A shape: every label present, one per line, colon-separated.
ABERTURA_TODOS_OS_ROTULOS = (
    "IMÓVEL: Um lote de terreno sob o nº 7 da quadra B, situado na Rua das "
    "Acácias Inventadas, com a área de 250,00m².\n"
    "CADASTRO MUNICIPAL: Contribuinte nº 123.456.7-8.\n"
    "PROPRIETÁRIOS: FULANO DE TESTE EXEMPLAR, brasileiro, casado.\n"
    "REGISTRO ANTERIOR: Matrícula nº 2.001 deste registro.\n"
)

# Provider B shape: PROPRIETÁRIOS folded into the imóvel paragraph, no label.
ABERTURA_SEM_PROPRIETARIOS = (
    "IMÓVEL: Um apartamento nº 42, localizado no 4º andar do Edifício "
    "Modelo, com área privativa de 85,00m², de propriedade de FULANO DE "
    "TESTE EXEMPLAR.\n"
    "CADASTRO MUNICIPAL: Contribuinte nº 998.877-6.\n"
    "REGISTRO ANTERIOR: Matrícula nº 5.500 deste registro.\n"
)

# Real-shaped closing, "O Oficial," variant — modelled on a production
# document's structure only (invented lot/cadastro/matrícula numbers, city,
# date and officer name).
ABERTURA_FECHO_OFICIAL = (
    "IMÓVEL: Um lote de terreno sob o nº 15 da quadra C, situado na Rua das "
    "Palmeiras Inventadas, com a área de 300,00m², confrontando com parte "
    "do lote nº 20, e com os lotes nºs 18 e 19.\n"
    "\n"
    "CADASTRO MUNICIPAL: Contribuinte nº 456.789-0.\n"
    "\n"
    "PROPRIETÁRIOS: FULANO DE TESTE EXEMPLAR, brasileiro, casado.\n"
    "\n"
    "REGISTRO ANTERIOR: R-05/M-12.345 de 10/02/1995, do Registro de "
    "Imóveis de Osasco/SP.\n"
    "\n"
    "Cotia, 20 de junho de 2018. O Oficial, ________ (Fulano Exemplo da "
    "Silva).\n"
)

# Same shape, "O Oficial Substituto," variant.
ABERTURA_FECHO_SUBSTITUTO = (
    "IMÓVEL: Um apartamento nº 55, no 5º andar do Edifício Exemplo, com "
    "área privativa de 90,00m².\n"
    "\n"
    "CADASTRO MUNICIPAL: Contribuinte nº 998.877-6.\n"
    "\n"
    "REGISTRO ANTERIOR: R-11/M-33.221 de 05/04/2001, do Registro de "
    "Imóveis de Campinas/SP.\n"
    "\n"
    "Cotia, 01 de setembro de 2015. O Oficial Substituto, ________ "
    "(Beltrana Exemplo Souza).\n"
)

TODAS_AS_ABERTURAS = (
    ABERTURA_TODOS_OS_ROTULOS,
    ABERTURA_SEM_PROPRIETARIOS,
    ABERTURA_FECHO_OFICIAL,
    ABERTURA_FECHO_SUBSTITUTO,
)


def _segmentar(texto: str) -> tuple[BlocoAbertura, ...]:
    return segmentar_abertura(texto, 0, len(texto))


class TestTodosOsRotulos:
    def test_four_blocks_in_document_order(self):
        blocos = _segmentar(ABERTURA_TODOS_OS_ROTULOS)
        assert [b.campo for b in blocos] == [
            "descricao_imovel",
            "cadastro_municipal",
            "proprietarios",
            "registro_anterior",
        ]

    def test_offsets_slice_back_to_the_right_value(self):
        texto = ABERTURA_TODOS_OS_ROTULOS
        blocos = _segmentar(texto)
        valores = {b.campo: texto[b.start : b.end].strip() for b in blocos}
        assert valores["descricao_imovel"].startswith("Um lote de terreno")
        assert valores["descricao_imovel"].endswith("250,00m².")
        assert valores["cadastro_municipal"] == "Contribuinte nº 123.456.7-8."
        assert valores["proprietarios"] == (
            "FULANO DE TESTE EXEMPLAR, brasileiro, casado."
        )
        assert valores["registro_anterior"] == (
            "Matrícula nº 2.001 deste registro."
        )

    def test_descricao_imovel_excludes_the_label(self):
        texto = ABERTURA_TODOS_OS_ROTULOS
        bloco = next(b for b in _segmentar(texto) if b.campo == "descricao_imovel")
        assert "IMOVEL" not in texto[bloco.start : bloco.end].upper()

    def test_rotulo_span_is_exactly_the_label_token(self):
        texto = ABERTURA_TODOS_OS_ROTULOS
        bloco = next(b for b in _segmentar(texto) if b.campo == "descricao_imovel")
        assert texto[bloco.rotulo_start : bloco.rotulo_end] == "IMÓVEL"
        assert bloco.rotulo_end <= bloco.start


class TestRotuloAusente:
    def test_missing_proprietarios_yields_no_block_not_a_wrong_one(self):
        blocos = _segmentar(ABERTURA_SEM_PROPRIETARIOS)
        campos = [b.campo for b in blocos]
        assert campos == ["descricao_imovel", "cadastro_municipal", "registro_anterior"]
        assert "proprietarios" not in campos

    def test_last_block_runs_to_the_end_of_the_window_minus_trailing_whitespace(self):
        # No _FIM_ABERTURA terminator in this fixture, so the fallback is
        # `end` — but the value is still trimmed of the trailing "\n".
        texto = ABERTURA_SEM_PROPRIETARIOS
        blocos = _segmentar(texto)
        assert texto[blocos[-1].end :] == "\n"
        assert texto[blocos[-1].start : blocos[-1].end] == (
            "Matrícula nº 5.500 deste registro."
        )

    def test_no_labels_at_all_yields_no_blocks(self):
        assert _segmentar("Apenas um parágrafo qualquer, sem rótulos.\n") == ()


class TestToleranciaDeRotulo:
    def test_lowercase_and_dash_separator(self):
        texto = "imóvel - Um terreno urbano ficticio.\n"
        blocos = _segmentar(texto)
        assert len(blocos) == 1
        assert blocos[0].campo == "descricao_imovel"
        assert texto[blocos[0].start : blocos[0].end].strip() == "Um terreno urbano ficticio."

    def test_no_separator_at_all_still_recognised(self):
        texto = "IMOVEL Um terreno urbano ficticio.\n"
        blocos = _segmentar(texto)
        assert len(blocos) == 1
        assert texto[blocos[0].start : blocos[0].end].strip() == "Um terreno urbano ficticio."

    def test_singular_and_feminine_proprietario_variants(self):
        for rotulo in ("PROPRIETÁRIO", "PROPRIETÁRIA", "PROPRIETÁRIOS", "PROPRIETÁRIAS"):
            texto = f"{rotulo}: Fulano de Teste.\n"
            blocos = _segmentar(texto)
            assert [b.campo for b in blocos] == ["proprietarios"], rotulo

    def test_registro_anterior_recognised_mid_document(self):
        texto = (
            "IMÓVEL: Um terreno.\n"
            "REGISTRO ANTERIOR: Matrícula nº 10.\n"
        )
        blocos = _segmentar(texto)
        assert [b.campo for b in blocos] == ["descricao_imovel", "registro_anterior"]


class TestPalavraNoMeioDeFraseNaoAbreBloco:
    def test_imovel_mentioned_mid_sentence_is_not_a_label(self):
        texto = (
            "IMÓVEL: Um terreno.\n"
            "REGISTRO ANTERIOR: originado do imóvel matriculado sob o nº 10, "
            "sem outras anotações.\n"
        )
        blocos = _segmentar(texto)
        # Exactly the two line-start labels — the "imóvel" mid the second
        # line's prose is not a second descricao_imovel block.
        assert [b.campo for b in blocos] == ["descricao_imovel", "registro_anterior"]

    def test_registro_anterior_word_mid_sentence_does_not_reopen_a_block(self):
        texto = (
            "CADASTRO MUNICIPAL: Contribuinte nº 1, conforme registro anterior "
            "já cancelado.\n"
        )
        blocos = _segmentar(texto)
        assert [b.campo for b in blocos] == ["cadastro_municipal"]


class TestFechoDaAbertura:
    """The regression found against real documents: the last block stopping
    before the closing locale+date and the officer's signature."""

    def test_oficial_variant_stops_before_the_closing(self):
        texto = ABERTURA_FECHO_OFICIAL
        blocos = _segmentar(texto)
        ultimo = blocos[-1]
        assert ultimo.campo == "registro_anterior"
        valor = texto[ultimo.start : ultimo.end]
        assert valor == (
            "R-05/M-12.345 de 10/02/1995, do Registro de Imóveis de Osasco/SP."
        )
        assert "Cotia" not in valor
        assert "Oficial" not in valor

    def test_oficial_substituto_variant_stops_before_the_closing(self):
        texto = ABERTURA_FECHO_SUBSTITUTO
        blocos = _segmentar(texto)
        ultimo = blocos[-1]
        assert ultimo.campo == "registro_anterior"
        valor = texto[ultimo.start : ultimo.end]
        assert valor == (
            "R-11/M-33.221 de 05/04/2001, do Registro de Imóveis de Campinas/SP."
        )
        assert "Cotia" not in valor
        assert "Substituto" not in valor

    def test_earlier_blocks_are_unaffected_by_the_closing_terminator(self):
        for texto in (ABERTURA_FECHO_OFICIAL, ABERTURA_FECHO_SUBSTITUTO):
            blocos = _segmentar(texto)
            campos = [b.campo for b in blocos]
            assert campos[0] == "descricao_imovel"
            assert campos[-1] == "registro_anterior"
            # No spillover: every block's own text stays inside itself.
            for a, b in zip(blocos, blocos[1:]):
                assert a.end <= b.start


class TestNenhumBlocoComEspacoNasBordas:
    def test_no_block_starts_or_ends_with_whitespace_on_any_fixture(self):
        for texto in TODAS_AS_ABERTURAS:
            for b in _segmentar(texto):
                valor = texto[b.start : b.end]
                assert valor == valor.strip(), (texto, b)
                assert valor  # trimming never eats the whole value here


class TestOffsetsSaoValidos:
    def test_every_block_is_a_valid_slice(self):
        for texto in TODAS_AS_ABERTURAS:
            for b in _segmentar(texto):
                assert 0 <= b.rotulo_start <= b.rotulo_end <= b.start <= b.end <= len(texto)
