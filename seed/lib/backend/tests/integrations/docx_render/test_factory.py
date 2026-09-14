"""get_docx_render_adapter — picks Fake vs Real(docxtpl) per the factory shape."""

from __future__ import annotations

from noctusai_lib.integrations.docx_render import (
    DocxtplRenderAdapter,
    FakeDocxRenderAdapter,
    get_docx_render_adapter,
)


def test_real_false_returns_fake() -> None:
    adapter = get_docx_render_adapter(real=False)
    assert isinstance(adapter, FakeDocxRenderAdapter)
    assert adapter.backend == "fake"


def test_real_true_returns_docxtpl() -> None:
    adapter = get_docx_render_adapter(real=True)
    assert isinstance(adapter, DocxtplRenderAdapter)
    assert adapter.backend == "docxtpl"


def test_default_is_real() -> None:
    assert isinstance(get_docx_render_adapter(), DocxtplRenderAdapter)
