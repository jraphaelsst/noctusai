"""DocxtplRenderAdapter — real rendering via `docxtpl`.

These exercise the actual `docxtpl` path (the dep ships in seed). If
`docxtpl` is somehow absent the suite fails loudly (ImportError) rather
than passing vacuously — matching `svg_render`'s real-adapter test
convention.
"""

from __future__ import annotations

import pytest

from noctusai_lib.integrations.docx_render import (
    DocxtplRenderAdapter,
    MissingPlaceholderError,
)

from ._helpers import (
    conditional_and_loop_docx,
    read_all_paragraph_text,
    read_paragraph_text,
    read_table_rows,
    simple_placeholder_docx,
)

# Deliberately nasty literal text: typos, accents, a quote, an apostrophe,
# an ampersand, angle brackets (would break naive raw-XML insertion), and
# an embedded newline. The exact string a legal clause quoting a matrícula
# might contain.
_LITERAL_TEXT = (
    "matricula 123 (typo, no accent) vs matrícula (correct); "
    '"quoted clause" it’s & <not a tag> R$ 10,00\n'
    "segunda linha do texto"
)


def test_literal_text_round_trips_byte_identical() -> None:
    template = simple_placeholder_docx("Clausula: {{ texto }}")
    adapter = DocxtplRenderAdapter()
    rendered = adapter.render(template, {"texto": _LITERAL_TEXT})
    readback = read_paragraph_text(rendered)
    assert readback == f"Clausula: {_LITERAL_TEXT}"


def test_literal_text_no_filters_applied() -> None:
    # A value containing what LOOKS like a Jinja tag must stay literal —
    # the adapter applies no filters and does not re-interpret substituted
    # values as template source.
    template = simple_placeholder_docx("{{ texto }}")
    adapter = DocxtplRenderAdapter()
    literal = "{{ not_a_variable }} {% not a tag %}"
    rendered = adapter.render(template, {"texto": literal})
    assert read_paragraph_text(rendered) == literal


def test_newline_becomes_word_line_break_and_reads_back_identical() -> None:
    # Documents the newline-handling contract: docxtpl converts an
    # embedded \n into a real Word line break (<w:br/>, splitting the run)
    # rather than leaving a literal \n character inside one <w:t> run — so
    # the text actually wraps in Word. python-docx's own `.text` property
    # reconstructs \n from <w:br/> on read, so the round trip is still
    # byte-identical including the newline.
    template = simple_placeholder_docx("{{ texto }}")
    adapter = DocxtplRenderAdapter()
    value = "linha 1\nlinha 2"
    rendered = adapter.render(template, {"texto": value})
    assert read_paragraph_text(rendered) == value

    import zipfile
    import io as _io

    with zipfile.ZipFile(_io.BytesIO(rendered)) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
    assert "<w:br/>" in xml
    assert "linha 1\nlinha 2" not in xml  # the raw \n is NOT left inline


def test_conditional_block_true_branch() -> None:
    template = conditional_and_loop_docx()
    adapter = DocxtplRenderAdapter()
    rendered = adapter.render(
        template,
        {
            "nome_contratante": "João",
            "tem_fiador": True,
            "nome_fiador": "Maria",
            "parcelas": [],
        },
    )
    paragraphs = read_all_paragraph_text(rendered)
    assert paragraphs[0] == "Contratante: João"
    assert paragraphs[1] == "Fiador: Maria"


def test_conditional_block_false_branch_skips_undefined_var() -> None:
    # tem_fiador=False means nome_fiador is never evaluated — StrictUndefined
    # must NOT fire for a variable the false branch never touches.
    template = conditional_and_loop_docx()
    adapter = DocxtplRenderAdapter()
    rendered = adapter.render(
        template,
        {"nome_contratante": "João", "tem_fiador": False, "parcelas": []},
    )
    paragraphs = read_all_paragraph_text(rendered)
    assert paragraphs[0] == "Contratante: João"
    assert paragraphs[1] == ""


def test_table_loop_repeats_row_per_item() -> None:
    template = conditional_and_loop_docx()
    adapter = DocxtplRenderAdapter()
    rendered = adapter.render(
        template,
        {
            "nome_contratante": "João",
            "tem_fiador": False,
            "parcelas": [
                {"numero": 1, "valor": "100,00"},
                {"numero": 2, "valor": "200,00"},
                {"numero": 3, "valor": "300,00"},
            ],
        },
    )
    rows = read_table_rows(rendered)
    assert rows == [
        ["1", "100,00"],
        ["2", "200,00"],
        ["3", "300,00"],
    ]


def test_missing_key_raises_typed_error_not_blank() -> None:
    template = simple_placeholder_docx("{{ nome_contratante }}")
    adapter = DocxtplRenderAdapter()
    with pytest.raises(MissingPlaceholderError):
        adapter.render(template, {})


def test_list_placeholders_simple() -> None:
    template = simple_placeholder_docx("Contrato: {{ nome_contratante }}")
    adapter = DocxtplRenderAdapter()
    assert adapter.list_placeholders(template) == {"nome_contratante"}


def test_list_placeholders_conditional_and_loop_root_names_only() -> None:
    # get_undeclared_template_variables() returns ROOT names — the loop
    # variable `p` (bound inside the `{% for %}`) must NOT appear, only
    # the iterable `parcelas` it iterates.
    template = conditional_and_loop_docx()
    adapter = DocxtplRenderAdapter()
    found = adapter.list_placeholders(template)
    assert found == {"nome_contratante", "tem_fiador", "nome_fiador", "parcelas"}
    assert "p" not in found


def test_completeness_gate_recipe() -> None:
    # The recipe the module docstring documents: list_placeholders(tpl) -
    # set(context) surfaces exactly what's missing, before render() spends
    # the render pass.
    template = simple_placeholder_docx("Contrato: {{ nome_contratante }}")
    adapter = DocxtplRenderAdapter()
    context = {}
    missing = adapter.list_placeholders(template) - set(context)
    assert missing == {"nome_contratante"}
