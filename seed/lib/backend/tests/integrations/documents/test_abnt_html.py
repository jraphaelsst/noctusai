"""`render_word_html` — a self-contained, Word-pasteable HTML fragment.

Every assertion here PARSES the emitted fragment with `html.parser`
(stdlib) rather than substring-matching the markup, so a real HTML
structural bug (like the double-quote-inside-a-double-quoted-attribute
defect this module's font-family value had to be fixed for — see
`abnt.py`'s `_HTML_STYLES` comment) fails the test instead of hiding
inside a string that merely LOOKS right.
"""
from __future__ import annotations

from html.parser import HTMLParser

from noctusai_lib.integrations.documents.abnt import render_word_html
from noctusai_lib.integrations.documents.formatting import (
    FormattedDocument,
    Paragraph,
    ParagraphKind,
    Run,
)


class _Recorder(HTMLParser):
    """Collects `(tag, attrs_dict)` opens and `data` text in order, and
    fails LOUD (via `HTMLParser`'s own error path) rather than silently
    reinterpreting malformed markup — the thing a raw substring match
    would never catch."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.events: list[tuple] = []

    def handle_starttag(self, tag, attrs):
        self.events.append(("start", tag, dict(attrs)))

    def handle_endtag(self, tag):
        self.events.append(("end", tag))

    def handle_data(self, data):
        if data.strip():
            self.events.append(("data", data))


def _parse(html: str) -> _Recorder:
    parser = _Recorder()
    parser.feed(html)
    parser.close()
    return parser


def _paragraph_styles(html: str) -> list[str]:
    parser = _parse(html)
    return [
        e[2]["style"]
        for e in parser.events
        if e[0] == "start" and e[1] == "p"
    ]


class TestSelfContained:
    def test_fragmento_nao_contem_bloco_style(self):
        doc = FormattedDocument(paragraphs=(Paragraph(runs=(Run("texto"),)),))
        html = render_word_html(doc)
        assert "<style" not in html.lower()

    def test_um_paragrafo_por_p(self):
        doc = FormattedDocument(paragraphs=(
            Paragraph(runs=(Run("um"),)),
            Paragraph(runs=(Run("dois"),)),
        ))
        html = render_word_html(doc)
        parser = _parse(html)
        p_opens = [e for e in parser.events if e[0] == "start" and e[1] == "p"]
        assert len(p_opens) == 2


class TestParagraphKindStyles:
    def test_body_justificado_com_recuo_de_primeira_linha(self):
        doc = FormattedDocument(paragraphs=(Paragraph(runs=(Run("corpo"),), kind=ParagraphKind.BODY),))
        style = _paragraph_styles(render_word_html(doc))[0]
        assert "text-align:justify" in style
        assert "text-indent:1.25cm" in style
        assert "font-size:12pt" in style
        assert "line-height:1.5" in style

    def test_title_centralizado_e_negrito(self):
        doc = FormattedDocument(paragraphs=(Paragraph(runs=(Run("Título"),), kind=ParagraphKind.TITLE),))
        style = _paragraph_styles(render_word_html(doc))[0]
        assert "text-align:center" in style
        assert "font-weight:bold" in style

    def test_heading_negrito_sem_indent(self):
        doc = FormattedDocument(paragraphs=(Paragraph(runs=(Run("Cláusula"),), kind=ParagraphKind.HEADING),))
        style = _paragraph_styles(render_word_html(doc))[0]
        assert "font-weight:bold" in style
        assert "text-indent" not in style

    def test_quote_recuo_4cm_fonte_10pt_espacamento_simples(self):
        doc = FormattedDocument(paragraphs=(Paragraph(runs=(Run("citação"),), kind=ParagraphKind.QUOTE),))
        style = _paragraph_styles(render_word_html(doc))[0]
        assert "margin-left:4cm" in style
        assert "font-size:10pt" in style
        assert "line-height:1;" in style

    def test_fonte_e_times_new_roman_com_fallback(self):
        doc = FormattedDocument(paragraphs=(Paragraph(runs=(Run("texto"),), kind=ParagraphKind.BODY),))
        style = _paragraph_styles(render_word_html(doc))[0]
        assert "'Times New Roman', Times, serif" in style

    def test_atributo_style_e_valido_apesar_das_aspas_no_font_family(self):
        # The regression this test exists for: a double-quoted font-family
        # value inside a double-quoted `style="..."` attribute would
        # terminate the attribute early. A parse that recovers exactly
        # ONE `style` attribute (not a truncated one plus stray text) is
        # the proof the fragment is syntactically valid HTML.
        doc = FormattedDocument(paragraphs=(Paragraph(runs=(Run("texto"),), kind=ParagraphKind.BODY),))
        html = render_word_html(doc)
        parser = _parse(html)
        p_events = [e for e in parser.events if e[0] == "start" and e[1] == "p"]
        assert len(p_events) == 1
        style = p_events[0][2]["style"]
        assert style.startswith("font-family:'Times New Roman'")


class TestInlineFormatting:
    def test_bold_run_vira_tag_b(self):
        doc = FormattedDocument(paragraphs=(Paragraph(runs=(Run("negrito", bold=True),)),))
        parser = _parse(render_word_html(doc))
        tags = [e[1] for e in parser.events if e[0] == "start"]
        assert "b" in tags

    def test_underline_run_vira_tag_u(self):
        doc = FormattedDocument(paragraphs=(Paragraph(runs=(Run("sublinhado", underline=True),)),))
        parser = _parse(render_word_html(doc))
        tags = [e[1] for e in parser.events if e[0] == "start"]
        assert "u" in tags

    def test_bold_e_underline_combinaveis(self):
        doc = FormattedDocument(paragraphs=(Paragraph(runs=(Run("ambos", bold=True, underline=True),)),))
        html = render_word_html(doc)
        parser = _parse(html)
        tags = [e[1] for e in parser.events if e[0] == "start"]
        assert "b" in tags and "u" in tags

    def test_title_forca_negrito_mesmo_sem_run_bold(self):
        doc = FormattedDocument(paragraphs=(Paragraph(runs=(Run("Sem formatação própria"),), kind=ParagraphKind.TITLE),))
        html = render_word_html(doc)
        parser = _parse(html)
        tags = [e[1] for e in parser.events if e[0] == "start"]
        assert "b" in tags

    def test_quebra_simples_vira_br(self):
        doc = FormattedDocument(paragraphs=(Paragraph(runs=(Run("linha 1\nlinha 2"),)),))
        html = render_word_html(doc)
        assert "<br>" in html
        parser = _parse(html)
        data = [e[1] for e in parser.events if e[0] == "data"]
        assert data == ["linha 1", "linha 2"]


class TestEscaping:
    def test_escapa_e_comercial_menor_e_maior_que(self):
        doc = FormattedDocument(paragraphs=(Paragraph(runs=(Run("A & B <tag> C > D"),)),))
        html = render_word_html(doc)
        assert "&amp;" in html
        assert "&lt;tag&gt;" in html
        # a well-formed fragment: the parser must read the escaped text
        # back as the ORIGINAL characters, not choke on a bare `<`/`>`.
        parser = _parse(html)
        data = "".join(e[1] for e in parser.events if e[0] == "data")
        assert data == "A & B <tag> C > D"

    def test_aspas_no_texto_nao_quebram_o_fragmento(self):
        doc = FormattedDocument(paragraphs=(Paragraph(runs=(Run('ele disse "olá"'),)),))
        html = render_word_html(doc)
        parser = _parse(html)
        p_events = [e for e in parser.events if e[0] == "start" and e[1] == "p"]
        assert len(p_events) == 1
        data = "".join(e[1] for e in parser.events if e[0] == "data")
        assert data == 'ele disse "olá"'
