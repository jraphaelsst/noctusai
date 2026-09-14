"""docx_render value objects, Protocol, and typed errors.

Mirrors the shape of ``integrations/svg_render/types.py`` — pure typing
module, zero third-party imports (the vendor SDK is lazy-imported inside
the real adapter only, per ``KB § PATTERNS/backend/seed-fake-real-adapter.md``).

Depends on ``documents.formatting`` (also zero third-party imports) for
the `Run` shape `rich_text()` accepts — see that method's docstring.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from noctusai_lib.integrations.documents.formatting import Run


class DocxRenderError(Exception):
    """Base class for every error `docx_render` raises."""


class MissingPlaceholderError(DocxRenderError):
    """A template variable was referenced by the template but absent from
    `context` at render time.

    The real adapter (`DocxtplRenderAdapter`) configures Jinja2's
    `StrictUndefined` so a missing key is REPORTED loudly — never
    silently rendered blank (`KB § 01-PHILOSOPHY.md § No silent errors`).
    Consumers should call `list_placeholders()` first to run a
    completeness gate (declared placeholders ⊆ context keys) before
    calling `render()`, so the failure surfaces before spending the
    render pass — this error is the backstop for the case they didn't.
    """


@runtime_checkable
class DocxRenderAdapter(Protocol):
    """DOCX-template render adapter contract. Both `FakeDocxRenderAdapter`
    and `DocxtplRenderAdapter` satisfy this Protocol naturally.

    - `render(template_bytes, context)` — fills a `.docx` Jinja-in-Word
      template (`docxtpl` syntax: `{{ var }}`, `{% if %}`, `{% for %}`)
      with `context` and returns the rendered `.docx` bytes. String
      values are inserted VERBATIM (see `MissingPlaceholderError` for the
      missing-key contract; see the module docstring for the literal-text
      + newline-handling guarantee).
    - `list_placeholders(template_bytes)` — every root variable name the
      template references (via `{{ }}`, `{% if %}`, `{% for x in %}`),
      independent of `context`. Lets a consumer run a completeness gate
      (`list_placeholders(tpl) - set(context)`) before `render()`.
    - `rich_text(runs)` — build a `render()`-context value for a
      docxtpl `{{r ... }}` inline-formatting slot (bold/underline PER
      RUN, e.g. a matrícula literal quote whose bold/underline must
      survive into the rendered `.docx`). A caller may NEVER `import
      docxtpl` itself to build this (`KB § 03-SEED-ARCHITECTURE.md`) —
      going through the adapter is the only sanctioned path, on both the
      Real (a genuine `docxtpl.RichText`) and Fake (a `FakeRichText`,
      no `docxtpl` import) sides. A PLAIN STRING in a `{{r ... }}` slot
      renders as EMPTY — docxtpl expects a `RichText`-shaped object
      there, not text — so this method exists precisely because there
      is no safe shortcut.
    """

    backend: str

    def render(self, template_bytes: bytes, context: Mapping[str, Any]) -> bytes: ...

    def list_placeholders(self, template_bytes: bytes) -> set[str]: ...

    def rich_text(self, runs: Sequence[Run]) -> Any: ...
