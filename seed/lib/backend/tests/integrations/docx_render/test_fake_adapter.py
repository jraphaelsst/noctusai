"""FakeDocxRenderAdapter — deterministic placeholder bytes + call recording."""

from __future__ import annotations

from noctusai_lib.integrations.docx_render import FakeDocxRenderAdapter

from ._helpers import conditional_and_loop_docx, simple_placeholder_docx


def test_fake_returns_valid_docx_bytes() -> None:
    template = simple_placeholder_docx("{{ nome }}")
    adapter = FakeDocxRenderAdapter()
    result = adapter.render(template, {"nome": "x"})
    # A valid .docx is a zip archive (PK magic bytes).
    assert result[:2] == b"PK"


def test_fake_is_deterministic() -> None:
    template = simple_placeholder_docx("{{ nome }}")
    a = FakeDocxRenderAdapter().render(template, {"nome": "x", "outro": "y"})
    b = FakeDocxRenderAdapter().render(template, {"nome": "x", "outro": "y"})
    assert a == b


def test_fake_varies_with_context_keys() -> None:
    template = simple_placeholder_docx("{{ nome }}")
    a = FakeDocxRenderAdapter().render(template, {"nome": "x"})
    b = FakeDocxRenderAdapter().render(template, {"outro": "x"})
    assert a != b


def test_fake_records_calls() -> None:
    template = simple_placeholder_docx("{{ nome }}")
    adapter = FakeDocxRenderAdapter()
    adapter.render(template, {"nome": "x", "b": 1})
    assert len(adapter.calls) == 1
    call = adapter.calls[0]
    assert call["context_keys"] == ["b", "nome"]
    assert len(call["template_sha256"]) == 64


def test_fake_list_placeholders_simple() -> None:
    template = simple_placeholder_docx("Contrato: {{ nome_contratante }}")
    adapter = FakeDocxRenderAdapter()
    assert adapter.list_placeholders(template) == {"nome_contratante"}


def test_fake_list_placeholders_conditional_and_loop() -> None:
    # Parity with DocxtplRenderAdapter: the `{% for p in parcelas %}` loop
    # target `p` is not a context key, so a completeness gate tested against
    # the Fake must not demand it.
    template = conditional_and_loop_docx()
    adapter = FakeDocxRenderAdapter()
    found = adapter.list_placeholders(template)
    assert found == {"nome_contratante", "tem_fiador", "nome_fiador", "parcelas"}


def test_fake_satisfies_protocol() -> None:
    from noctusai_lib.integrations.docx_render import DocxRenderAdapter

    assert isinstance(FakeDocxRenderAdapter(), DocxRenderAdapter)
