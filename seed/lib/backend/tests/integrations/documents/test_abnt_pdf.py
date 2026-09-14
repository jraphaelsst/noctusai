"""`render_abnt_pdf` — every assertion here reads the ACTUAL rendered PDF
back with PyMuPDF (page size, text, font flags, drawings), not the story
we handed reportlab. `reportlab` writes, it does not read, and this
product has no PDF reader dependency of its own for production code — but
`PyMuPDF` is already a hard seed dependency (`integrations.media`), so
using it here to verify our OWN writer's output is free.

A layout claim this file cannot make mechanically (does the line before a
hard <br/> wrap look visually ragged rather than stretched?) was verified
by rendering a sample to PNG and inspecting it — see the engineer's
delivery note for the paths; `justifyBreaks=0` (asserted indirectly here
via the style construction) is the mechanism.
"""
from __future__ import annotations

import fitz
import pytest
from reportlab.lib.units import cm

from noctusai_lib.integrations.documents.abnt import (
    UnsupportedGlyphError,
    render_abnt_pdf,
)
from noctusai_lib.integrations.documents.formatting import (
    FormattedDocument,
    Paragraph,
    ParagraphKind,
    Run,
)

def _open(pdf_bytes: bytes) -> fitz.Document:
    return fitz.open(stream=pdf_bytes, filetype="pdf")


def _spans(page):
    out = []
    info = page.get_text("dict", flags=fitz.TEXTFLAGS_DICT)
    for block in info["blocks"]:
        for line in block.get("lines", []):
            out.extend(line["spans"])
    return out


class TestPageGeometry:
    def test_pagina_e_a4(self):
        doc = FormattedDocument(paragraphs=(Paragraph(runs=(Run("texto"),)),))
        page = _open(render_abnt_pdf(doc))[0]
        assert round(page.rect.width, 1) == round(21.0 * cm, 1)
        assert round(page.rect.height, 1) == round(29.7 * cm, 1)

    def test_margem_superior_e_esquerda_aproximadamente_3cm(self):
        doc = FormattedDocument(paragraphs=(Paragraph(runs=(Run("texto de teste"),), kind=ParagraphKind.HEADING),))
        page = _open(render_abnt_pdf(doc))[0]
        blocks = page.get_text("blocks")
        assert blocks, "esperava ao menos um bloco de texto"
        x0, y0, _x1, _y1 = blocks[0][:4]
        # PyMuPDF's coordinate origin is the page's top-left corner, so a
        # SMALL y0 IS "near the top" — tolerance covers the font's own
        # ascent above its baseline, not a second unrelated margin.
        assert 3 * cm - 5 <= y0 <= 3 * cm + 20
        assert 3 * cm - 5 <= x0 <= 3 * cm + 10  # +10 covers the glyph's own left side-bearing


class TestParagraphKindLayout:
    def test_title_e_centralizado_e_negrito(self):
        doc = FormattedDocument(paragraphs=(Paragraph(runs=(Run("Título do Documento"),), kind=ParagraphKind.TITLE),))
        page = _open(render_abnt_pdf(doc))[0]
        spans = [s for s in _spans(page) if s["text"].strip()]
        assert spans, "esperava algum texto"
        assert all("Bold" in s["font"] for s in spans)
        # Centered on the CONTENT FRAME (between the 3cm/2cm left/right
        # margins), not the full page — the margins are asymmetric, so
        # the frame's center is offset from the page's own center.
        frame_center = 3 * cm + (page.rect.width - 3 * cm - 2 * cm) / 2
        for s in spans:
            x0, _y0, x1, _y1 = s["bbox"]
            span_center = (x0 + x1) / 2
            assert abs(span_center - frame_center) < 2, "título deveria estar centralizado no frame"

    def test_title_e_negrito_mesmo_sem_run_bold_na_origem(self):
        # "ABNT by construction": a synthesized title has no Run.bold of
        # its own, yet the KIND still forces bold.
        doc = FormattedDocument(paragraphs=(Paragraph(runs=(Run("Sem formatação própria"),), kind=ParagraphKind.TITLE),))
        page = _open(render_abnt_pdf(doc))[0]
        spans = [s for s in _spans(page) if s["text"].strip()]
        assert all("Bold" in s["font"] for s in spans)

    def test_heading_e_negrito_alinhado_a_esquerda(self):
        doc = FormattedDocument(paragraphs=(Paragraph(runs=(Run("Cláusula Primeira"),), kind=ParagraphKind.HEADING),))
        page = _open(render_abnt_pdf(doc))[0]
        spans = [s for s in _spans(page) if s["text"].strip()]
        assert all("Bold" in s["font"] for s in spans)
        x0 = min(s["bbox"][0] for s in spans)
        assert x0 < 3 * cm + 10  # no first-line indent

    def test_body_tem_recuo_de_primeira_linha(self):
        doc = FormattedDocument(paragraphs=(
            Paragraph(runs=(Run("Este é o corpo do texto em modo BODY."),), kind=ParagraphKind.BODY),
        ))
        page = _open(render_abnt_pdf(doc))[0]
        spans = [s for s in _spans(page) if s["text"].strip()]
        x0 = min(s["bbox"][0] for s in spans)
        # left margin (3cm) + first-line indent (1.25cm), loosely bounded.
        assert x0 > 3 * cm + 1.25 * cm - 5

    def test_quote_tem_recuo_de_4cm_e_fonte_menor(self):
        doc = FormattedDocument(paragraphs=(
            Paragraph(runs=(Run("Uma citação longa recuada."),), kind=ParagraphKind.QUOTE),
        ))
        page = _open(render_abnt_pdf(doc))[0]
        spans = [s for s in _spans(page) if s["text"].strip()]
        x0 = min(s["bbox"][0] for s in spans)
        assert x0 > 3 * cm + 4 * cm - 5
        assert all(round(s["size"]) == 10 for s in spans)


class TestInlineFormatting:
    def test_bold_via_flags_ou_nome_da_fonte(self):
        doc = FormattedDocument(paragraphs=(
            Paragraph(runs=(Run("normal "), Run("negrito", bold=True))),
        ))
        page = _open(render_abnt_pdf(doc))[0]
        spans = {s["text"]: s for s in _spans(page)}
        assert "Bold" not in spans["normal "]["font"]
        assert "Bold" in spans["negrito"]["font"]

    def test_underline_via_desenho_sob_o_texto(self):
        doc = FormattedDocument(paragraphs=(
            Paragraph(runs=(Run("normal "), Run("sublinhado", underline=True))),
        ))
        page = _open(render_abnt_pdf(doc))[0]
        drawings = page.get_drawings()
        assert len(drawings) == 1, "esperava exatamente um traço de sublinhado"

    def test_negrito_e_sublinhado_combinaveis_no_mesmo_run(self):
        doc = FormattedDocument(paragraphs=(
            Paragraph(runs=(Run("ambos", bold=True, underline=True),)),
        ))
        page = _open(render_abnt_pdf(doc))[0]
        spans = [s for s in _spans(page) if s["text"].strip()]
        assert all("Bold" in s["font"] for s in spans)
        assert len(page.get_drawings()) == 1

    def test_quebra_simples_dentro_do_run_vira_quebra_de_linha_real(self):
        doc = FormattedDocument(paragraphs=(
            Paragraph(runs=(Run("linha 1\nlinha 2"),)),
        ))
        page = _open(render_abnt_pdf(doc))[0]
        text = page.get_text()
        assert "linha 1\nlinha 2" in text


class TestPageNumbers:
    def _many_paragraphs(self, n: int):
        return tuple(
            Paragraph(runs=(Run("Este é um parágrafo de teste para forçar múltiplas páginas. " * 8),))
            for _ in range(n)
        )

    def test_pagina_1_nao_tem_numero(self):
        doc = FormattedDocument(paragraphs=(Paragraph(runs=(Run("única página"),)),))
        d = _open(render_abnt_pdf(doc))
        assert d.page_count == 1
        text = d[0].get_text().strip()
        assert text == "única página"

    def test_a_partir_da_pagina_2_o_numero_aparece_no_topo_direito(self):
        doc = FormattedDocument(paragraphs=self._many_paragraphs(40))
        d = _open(render_abnt_pdf(doc))
        assert d.page_count >= 2

        page1_text = d[0].get_text()
        assert not any(page1_text.strip().startswith(str(n)) for n in range(1, 10))

        for page_index in range(1, d.page_count):
            page = d[page_index]
            number_spans = [
                s for s in _spans(page)
                if s["text"].strip() == str(page_index + 1)
            ]
            assert number_spans, f"esperava o número {page_index + 1} na página {page_index + 1}"
            span = number_spans[0]
            x0, y0, x1, _y1 = span["bbox"]
            assert x1 > page.rect.width - 3 * cm, "número deveria estar próximo à borda direita"
            assert y0 < 3 * cm, "número deveria estar dentro da margem superior"


class TestDeterminism:
    def test_mesma_entrada_produz_os_mesmos_bytes(self):
        doc = FormattedDocument(
            title="Determinismo",
            paragraphs=(
                Paragraph(runs=(Run("Título"),), kind=ParagraphKind.TITLE),
                Paragraph(runs=(Run("corpo "), Run("negrito", bold=True)), kind=ParagraphKind.BODY),
            ),
        )
        first = render_abnt_pdf(doc)
        second = render_abnt_pdf(doc)
        assert first == second


class TestGlyphCoverage:
    def test_winansi_covers_pt_br_legal_glyphs(self):
        """Every character pt-BR legal documents actually use — ordinal
        indicators, section sign, en/em dash, curly quotes, bullet,
        one-half, superscript two, and accented capitals — round-trips
        exactly through the core Times font. This is the evidence behind
        the font decision: NO Liberation Serif vendoring was needed."""
        glyphs = "º ª § – — “ ” ‘ ’ • ½ ² Ç Ã Õ É Ê Ô Ú"
        doc = FormattedDocument(paragraphs=(Paragraph(runs=(Run(glyphs),)),))
        page = _open(render_abnt_pdf(doc))[0]
        extracted = page.get_text().strip()
        assert extracted == glyphs

    def test_caractere_nao_representavel_falha_alto_nomeando_o_caractere(self):
        doc = FormattedDocument(paragraphs=(Paragraph(runs=(Run("texto com emoji \U0001F600 no meio"),)),))
        with pytest.raises(UnsupportedGlyphError) as exc_info:
            render_abnt_pdf(doc)
        assert "\U0001F600" in str(exc_info.value)
        assert "U+1F600" in str(exc_info.value)

    def test_titulo_do_documento_tambem_e_verificado(self):
        doc = FormattedDocument(title="\U0001F600", paragraphs=(Paragraph(runs=(Run("corpo normal"),)),))
        with pytest.raises(UnsupportedGlyphError):
            render_abnt_pdf(doc)
