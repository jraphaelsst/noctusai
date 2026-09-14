"""DocxtplRenderAdapter — real DOCX template rendering via `docxtpl`.

Lazy import — `docxtpl` + `jinja2` are imported inside the method bodies,
guarded by `try/except ImportError`, so the seed stays importable on a
machine without `docxtpl` installed (the Fake path is the dev/test
default). Mirrors `svg_render.ResvgRenderAdapter`'s lazy-import shape.

**Literal-text + XML-safety contract.** The adapter builds a
`jinja2.Environment(autoescape=True, undefined=StrictUndefined)` and
applies NO filters of its own — string values from `context` are
substituted verbatim. `autoescape=True` is the correct, defensive
default for XML content (some templating paths route interpolated text
through Jinja's own escaper before `docxtpl` maps it into the OOXML
tree); regardless of that path, `python-docx`/`lxml`'s XML SERIALIZATION
on save always escapes `&`, `<`, `>` in text content (mandatory for
well-formed XML) and leaves quotes/apostrophes untouched (legal
unescaped in XML text). Both are transparent to the reader: a consumer
that reads the rendered `.docx` back via `python-docx`'s `paragraph.text`
(or any XML-aware reader) gets the ORIGINAL literal string back,
byte-for-byte — see `test_docxtpl_adapter.py::test_literal_text_*`.

**Newline handling.** `docxtpl` converts an embedded `\\n` in a context
value into a real Word line break (`<w:br/>`, splitting the text run at
that point) rather than leaving a literal `\\n` character sitting inside
one `<w:t>` run — so a multi-line string actually WRAPS in Word instead
of being silently collapsed to one line (Word does not treat a raw `\\n`
inside `<w:t>` as a line break). Reading it back via `python-docx`'s
`.text` property reconstructs the `\\n` from the `<w:br/>`, so the
round-trip through `render()` → `.text` is still byte-identical to the
original string, `\\n` included.

**Missing-key contract.** `StrictUndefined` makes a reference to a
context key that is absent (and actually evaluated — a `{% if %}`
branch that never runs is never evaluated) raise
`jinja2.exceptions.UndefinedError`, which this adapter re-raises as
`MissingPlaceholderError` — never a silently-blank substitution.
"""

from __future__ import annotations

import io
from typing import Any, Mapping

from noctusai_lib.integrations.docx_render.types import MissingPlaceholderError

_IMPORT_HINT = (
    "docxtpl is not installed — install it to use DocxtplRenderAdapter, "
    "or use FakeDocxRenderAdapter (get_docx_render_adapter(real=False))."
)


class DocxtplRenderAdapter:
    """Real DOCX template render adapter via `docxtpl` (Jinja-in-Word)."""

    backend = "docxtpl"

    def render(self, template_bytes: bytes, context: Mapping[str, Any]) -> bytes:
        try:
            import jinja2
            from docxtpl import DocxTemplate
        except ImportError as exc:  # pragma: no cover - exercised via factory real=False default
            raise RuntimeError(_IMPORT_HINT) from exc

        env = jinja2.Environment(autoescape=True, undefined=jinja2.StrictUndefined)
        doc = DocxTemplate(io.BytesIO(template_bytes))
        try:
            doc.render(dict(context), jinja_env=env, autoescape=True)
        except jinja2.exceptions.UndefinedError as exc:
            raise MissingPlaceholderError(
                f"template references a variable missing from context: {exc}"
            ) from exc

        out = io.BytesIO()
        doc.save(out)
        return out.getvalue()

    def list_placeholders(self, template_bytes: bytes) -> set[str]:
        try:
            from docxtpl import DocxTemplate
        except ImportError as exc:  # pragma: no cover - exercised via factory real=False default
            raise RuntimeError(_IMPORT_HINT) from exc

        doc = DocxTemplate(io.BytesIO(template_bytes))
        return set(doc.get_undeclared_template_variables())
