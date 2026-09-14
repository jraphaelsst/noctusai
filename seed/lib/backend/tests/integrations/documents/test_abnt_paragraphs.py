"""`paragraphs_from_text` and `paragraphs_from_docx` — plain text / `.docx`
→ `Paragraph`s. The renderers (`render_abnt_pdf`/`render_word_html`) are
covered separately; this file is pure-Python logic only."""
from __future__ import annotations

import io

import docx
import pytest

from noctusai_lib.integrations.documents.abnt import (
    paragraphs_from_docx,
    paragraphs_from_text,
)
from noctusai_lib.integrations.documents.formatting import FormatRange, ParagraphKind


def _runs(paragraphs):
    return [[(r.text, r.bold, r.underline) for r in p.runs] for p in paragraphs]


class TestParagraphsFromTextSplitting:
    def test_texto_sem_quebra_e_um_unico_paragrafo(self):
        paras = paragraphs_from_text("uma linha só")
        assert len(paras) == 1
        assert paras[0].text == "uma linha só"
        assert paras[0].kind == ParagraphKind.BODY

    def test_uma_linha_em_branco_separa_paragrafos(self):
        paras = paragraphs_from_text("primeiro\n\nsegundo")
        assert [p.text for p in paras] == ["primeiro", "segundo"]

    def test_varias_linhas_em_branco_colapsam_em_uma_unica_quebra(self):
        paras = paragraphs_from_text("primeiro\n\n\n\nsegundo")
        assert [p.text for p in paras] == ["primeiro", "segundo"]

    def test_quebra_simples_permanece_dentro_do_run(self):
        paras = paragraphs_from_text("linha 1\nlinha 2")
        assert len(paras) == 1
        assert paras[0].text == "linha 1\nlinha 2"
        assert paras[0].runs[0].text == "linha 1\nlinha 2"

    def test_texto_vazio_nao_gera_paragrafos(self):
        assert paragraphs_from_text("") == ()

    def test_texto_so_com_linhas_em_branco_nao_gera_paragrafos(self):
        assert paragraphs_from_text("\n\n\n\n") == ()

    def test_kind_se_aplica_a_todos_os_paragrafos_gerados(self):
        paras = paragraphs_from_text("um\n\ndois", kind=ParagraphKind.QUOTE)
        assert all(p.kind == ParagraphKind.QUOTE for p in paras)


class TestParagraphsFromTextFormatting:
    def test_split_exatamente_nas_bordas_do_range(self):
        # "AB[CD]EF" — offsets: A=0 B=1 C=2 D=3 E=4 F=5
        paras = paragraphs_from_text("ABCDEF", (FormatRange(2, 4, bold=True),))
        assert _runs(paras) == [[("AB", False, False), ("CD", True, False), ("EF", False, False)]]

    def test_ranges_sobrepostos_compoem_bold_e_underline(self):
        # bold covers [2,7), underline covers [4,9) — overlap [4,7) is both.
        paras = paragraphs_from_text(
            "ABCDEFGHIJ",
            (FormatRange(2, 7, bold=True), FormatRange(4, 9, underline=True)),
        )
        assert _runs(paras) == [[
            ("AB", False, False),
            ("CD", True, False),
            ("EFG", True, True),
            ("HI", False, True),
            ("J", False, False),
        ]]

    def test_range_cruzando_fronteira_de_paragrafo_e_clipado_por_lado(self):
        # "ABC\n\nDEF" offsets: A=0 B=1 C=2 \n=3 \n=4 D=5 E=6 F=7
        # range [1,6) covers "BC" (end of p1) and "DE" (start of p2).
        paras = paragraphs_from_text("ABC\n\nDEF", (FormatRange(1, 6, bold=True),))
        assert _runs(paras) == [
            [("A", False, False), ("BC", True, False)],
            [("D", True, False), ("EF", False, False)],
        ]

    def test_range_totalmente_fora_do_paragrafo_e_descartado(self):
        paras = paragraphs_from_text("ABC\n\nDEF", (FormatRange(0, 3, bold=True),))
        assert _runs(paras)[1] == [("DEF", False, False)]

    def test_runs_adjacentes_com_mesma_formatacao_sao_mesclados(self):
        # two abutting ranges with identical formatting must not split the
        # word in two — the merge collapses them back into one Run.
        paras = paragraphs_from_text(
            "ABCDEF",
            (FormatRange(0, 3, bold=True), FormatRange(3, 6, bold=True)),
        )
        assert _runs(paras) == [[("ABCDEF", True, False)]]


class TestParagraphsFromDocx:
    def _docx_bytes(self, doc: "docx.document.Document") -> bytes:
        buf = io.BytesIO()
        doc.save(buf)
        return buf.getvalue()

    def test_runs_com_bold_e_underline_explicitos_sao_preservados(self):
        doc = docx.Document()
        p = doc.add_paragraph()
        p.add_run("plano ")
        b = p.add_run("negrito")
        b.bold = True
        u = p.add_run(" sublinhado")
        u.underline = True

        paras = paragraphs_from_docx(self._docx_bytes(doc))
        assert len(paras) == 1
        assert _runs(paras)[0] == [
            ("plano ", False, False),
            ("negrito", True, False),
            (" sublinhado", False, True),
        ]

    def test_bold_efetivo_herda_do_estilo_do_paragrafo(self):
        doc = docx.Document()
        doc.add_paragraph("Cláusula Primeira", style="Heading 1")

        paras = paragraphs_from_docx(self._docx_bytes(doc))
        assert paras[0].runs[0].bold is True

    def test_bold_explicito_do_run_sobrepoe_o_estilo(self):
        doc = docx.Document()
        p = doc.add_paragraph(style="Heading 1")
        r = p.add_run("não negrito apesar do estilo")
        r.bold = False

        paras = paragraphs_from_docx(self._docx_bytes(doc))
        assert paras[0].runs[0].bold is False

    def test_classify_escolhe_o_kind_por_nome_de_estilo(self):
        doc = docx.Document()
        doc.add_paragraph("Título", style="Title")
        doc.add_paragraph("Cláusula Primeira", style="Heading 1")
        doc.add_paragraph("corpo comum")

        def classify(style_name: str, text: str) -> ParagraphKind:
            if "Title" in style_name:
                return ParagraphKind.TITLE
            if "Heading" in style_name:
                return ParagraphKind.HEADING
            return ParagraphKind.BODY

        paras = paragraphs_from_docx(self._docx_bytes(doc), classify=classify)
        assert [p.kind for p in paras] == [
            ParagraphKind.TITLE,
            ParagraphKind.HEADING,
            ParagraphKind.BODY,
        ]

    def test_sem_classify_todo_paragrafo_e_body(self):
        doc = docx.Document()
        doc.add_paragraph("Título", style="Title")

        paras = paragraphs_from_docx(self._docx_bytes(doc))
        assert paras[0].kind == ParagraphKind.BODY

    def test_paragrafos_vazios_sao_descartados(self):
        doc = docx.Document()
        doc.add_paragraph("primeiro")
        doc.add_paragraph("")
        doc.add_paragraph("segundo")

        paras = paragraphs_from_docx(self._docx_bytes(doc))
        assert [p.text for p in paras] == ["primeiro", "segundo"]

    def test_runs_adjacentes_com_mesma_formatacao_sao_mesclados(self):
        doc = docx.Document()
        p = doc.add_paragraph()
        r1 = p.add_run("um ")
        r1.bold = True
        r2 = p.add_run("dois")
        r2.bold = True

        paras = paragraphs_from_docx(self._docx_bytes(doc))
        assert len(paras[0].runs) == 1
        assert paras[0].runs[0].text == "um dois"
