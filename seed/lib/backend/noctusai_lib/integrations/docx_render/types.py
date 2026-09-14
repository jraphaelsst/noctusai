"""docx_render value objects, Protocol, and typed errors.

Mirrors the shape of ``integrations/svg_render/types.py`` — pure typing
module, zero third-party imports (the vendor SDK is lazy-imported inside
the real adapter only, per ``KB § PATTERNS/backend/seed-fake-real-adapter.md``).
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable


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
    """

    backend: str

    def render(self, template_bytes: bytes, context: Mapping[str, Any]) -> bytes: ...

    def list_placeholders(self, template_bytes: bytes) -> set[str]: ...
