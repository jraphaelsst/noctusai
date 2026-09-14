"""DOCX template-render seed primitive — Protocol + Fake + Real(docxtpl) + factory.

Built for the `contract-automation` project's seed half (Slice S-c, F5):
a product (e.g. a future contract-generation product) needs to fill a
`.docx` Jinja-in-Word template — literal-text substitution (legal
paragraphs quoting a matrícula, verbatim typos and all), conditional
blocks (`{% if %}`), and repeating table rows (`{% for %}` over
`parcelas`) — and get back rendered `.docx` bytes.

**What ships** (`KB § PATTERNS/backend/seed-fake-real-adapter.md` shape):

- `DocxRenderAdapter` Protocol (`types.py`) — `render()` + `list_placeholders()`
  + `rich_text()`.
- `MissingPlaceholderError` / `DocxRenderError` — typed errors; a missing
  context key is REPORTED, never silently rendered blank.
- `FakeDocxRenderAdapter` (+ its `rich_text()` return value `FakeRichText`)
  — deterministic in-memory implementation, no `docxtpl` dependency
  (dev/test default).
- `DocxtplRenderAdapter` — real rendering via `docxtpl` (lazy-imported).
- `get_docx_render_adapter()` factory.

**Consume recipe:**

    from noctusai_lib.integrations.docx_render import get_docx_render_adapter

    adapter = get_docx_render_adapter(real=True)          # prod
    missing = adapter.list_placeholders(template_bytes) - set(context)
    if missing:
        raise ValueError(f"template needs: {sorted(missing)}")
    docx_bytes = adapter.render(template_bytes, context)

Tests inject `FakeDocxRenderAdapter` (or `real=False`) — never
monkeypatch the real adapter ([[di-test-seam]]).

**Licenses.** `docxtpl` is LGPL-2.1 — used here strictly server-side (the
platform's own backend renders the `.docx`; the library itself is never
redistributed to an end user), which does not trigger LGPL's
distribution/linking obligations. `python-docx` is MIT.

**Future consumer.** `products/knowledge-extractor/backend/app/services/
docx_export.py` hand-rolls a markdown→docx converter with its own direct
`python-docx` usage (methodology-doc export, not template-fill) — a
plausible future consumer of this module if/when it needs Jinja-style
template placeholders instead of markdown parsing. Not modified by this
change; noted here for the next agent that touches it.
"""

from __future__ import annotations

from noctusai_lib.integrations.docx_render.docxtpl_adapter import DocxtplRenderAdapter
from noctusai_lib.integrations.docx_render.fake_adapter import (
    FakeDocxRenderAdapter,
    FakeRichText,
)
from noctusai_lib.integrations.docx_render.types import (
    DocxRenderAdapter,
    DocxRenderError,
    MissingPlaceholderError,
)


def get_docx_render_adapter(*, real: bool = True) -> DocxRenderAdapter:
    """Return a DOCX-template render adapter.

    - `real=True` (default) -> `DocxtplRenderAdapter`. The `docxtpl`
      import is lazy (on first call), so construction never fails; a
      missing vendor lib raises a clear `RuntimeError` at call time
      rather than degrading silently.
    - `real=False` -> `FakeDocxRenderAdapter` (dev/test).
    """
    if not real:
        return FakeDocxRenderAdapter()
    return DocxtplRenderAdapter()


__all__ = [
    "DocxRenderAdapter",
    "DocxRenderError",
    "DocxtplRenderAdapter",
    "FakeDocxRenderAdapter",
    "FakeRichText",
    "MissingPlaceholderError",
    "get_docx_render_adapter",
]
