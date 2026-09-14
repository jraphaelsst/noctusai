"""`DocxRenderAdapter.rich_text(runs)` — Fake + Real parity, and the actual
`{{r ... }}` docxtpl round trip. Contract
`projects/abnt-formatting-CONTRACT.md` §5: a caller must NEVER `import
docxtpl` itself to build a rich-text context value — this method is the
only sanctioned path, on BOTH sides.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents.formatting import Run
from noctusai_lib.integrations.docx_render import (
    DocxtplRenderAdapter,
    FakeDocxRenderAdapter,
    FakeRichText,
)

from ._helpers import read_paragraph_text, simple_placeholder_docx


class TestFakeRichText:
    def test_stringifies_to_the_plain_text_concatenation(self) -> None:
        rt = FakeDocxRenderAdapter().rich_text(
            (Run("bold", bold=True), Run(" plain"), Run(" underline", underline=True))
        )
        assert isinstance(rt, FakeRichText)
        assert str(rt) == "bold plain underline"

    def test_never_imports_docxtpl(self) -> None:
        import sys

        # A prior test in this session may already have imported docxtpl —
        # the contract is about THIS module, not the process: `fake_adapter`
        # itself carries no top-level `docxtpl` import (see its own module
        # docstring), which `rich_text()` here does not change.
        import noctusai_lib.integrations.docx_render.fake_adapter as fake_adapter_mod

        assert "docxtpl" not in fake_adapter_mod.__dict__
        assert "docxtpl" not in dir(fake_adapter_mod)


class TestDocxtplRichText:
    def test_returns_a_real_docxtpl_richtext(self) -> None:
        from docxtpl import RichText

        rt = DocxtplRenderAdapter().rich_text((Run("negrito", bold=True),))
        assert isinstance(rt, RichText)

    def test_bold_and_underline_survive_the_r_tag_round_trip(self) -> None:
        template = simple_placeholder_docx("Antes: {{r quote }} depois.")
        adapter = DocxtplRenderAdapter()
        rt = adapter.rich_text(
            (Run("negrito", bold=True), Run(" comum"), Run(" sublinhado", underline=True))
        )
        rendered = adapter.render(template, {"quote": rt})
        assert read_paragraph_text(rendered) == "Antes: negrito comum sublinhado depois."

        import io
        import zipfile

        with zipfile.ZipFile(io.BytesIO(rendered)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8")
        assert "<w:b/>" in xml and "<w:u " in xml

    def test_a_plain_string_in_an_r_slot_renders_empty_hence_this_method_exists(self) -> None:
        # Documents WHY `rich_text()` exists at all: a `{{r ... }}` slot is
        # not a normal Jinja substitution — handing it a bare string is a
        # silent content-loss bug, not a type error.
        template = simple_placeholder_docx("Antes: {{r quote }} depois.")
        adapter = DocxtplRenderAdapter()
        rendered = adapter.render(template, {"quote": "texto simples"})
        assert "texto simples" not in read_paragraph_text(rendered)

    def test_embedded_newline_becomes_a_real_line_break(self) -> None:
        template = simple_placeholder_docx("{{r quote }}")
        adapter = DocxtplRenderAdapter()
        rt = adapter.rich_text((Run("linha 1\nlinha 2", bold=True),))
        rendered = adapter.render(template, {"quote": rt})
        assert read_paragraph_text(rendered) == "linha 1\nlinha 2"

        import io
        import zipfile

        with zipfile.ZipFile(io.BytesIO(rendered)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8")
        assert "<w:br/>" in xml

    def test_empty_runs_render_as_empty_not_an_error(self) -> None:
        template = simple_placeholder_docx("Antes: {{r quote }} depois.")
        adapter = DocxtplRenderAdapter()
        rendered = adapter.render(template, {"quote": adapter.rich_text(())})
        assert read_paragraph_text(rendered) == "Antes:  depois."
