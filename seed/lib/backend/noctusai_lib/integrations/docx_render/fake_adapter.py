"""FakeDocxRenderAdapter — deterministic in-memory DOCX render for dev + tests.

Never imports `docxtpl` (that's the Real adapter's vendor SDK). Uses
`python-docx` only — a core seed dependency, not a lazy/optional one —
to build a valid, deterministic placeholder `.docx` so consumer code that
persists / hashes / re-opens `render()`'s return value works unchanged
under test, mirroring `FakeSvgRenderAdapter`'s "even the Fake returns
valid-format bytes" convention.

Records every call on `calls` (read-side test introspection) per
[[di-test-seam]] — never monkeypatch the real adapter.

`list_placeholders()` is a lightweight, dependency-free, best-effort
regex scan over the template's raw `word/*.xml` parts — NOT a full
Jinja2 parse. It extracts the root variable name from the common shapes:

- `{{ name }}` / `{{ name.attr }}` / `{{ name|filter }}`      -> `name`
- `{% if name %}` / `{% if name.attr %}`                      -> `name`
- `{% for x in name %}` / `{% for x, y in name %}`            -> `name`
- `{%tr for x in name %}` (docxtpl's table-row-repeat syntax) -> `name`

It will NOT resolve compound expressions (`{{ a if b else c }}`,
arithmetic, nested calls) the way `DocxtplRenderAdapter.list_placeholders`
(Jinja2 `meta.find_undeclared_variables`, the canonical answer) does —
use the Real adapter when exhaustive detection matters more than
avoiding the `docxtpl` import.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from typing import Any, Mapping

from docx import Document

_VAR_RE = re.compile(r"\{\{-?\s*([A-Za-z_][A-Za-z0-9_]*)")
_FOR_RE = re.compile(
    r"\{%-?\s*(?:tr\s+)?for\s+([A-Za-z_][A-Za-z0-9_]*"
    r"(?:\s*,\s*[A-Za-z_][A-Za-z0-9_]*)?)\s+in\s+([A-Za-z_][A-Za-z0-9_]*)"
)
_IF_RE = re.compile(r"\{%-?\s*(?:tr\s+)?if\s+([A-Za-z_][A-Za-z0-9_]*)")


class FakeDocxRenderAdapter:
    """Deterministic in-memory DOCX render adapter.

    `render()` never inspects `template_bytes` beyond hashing it — the
    returned bytes are a fixed-shape placeholder `.docx` (callers must
    NOT assume its content means anything beyond the recorded call). Two
    calls with identical `(template_bytes, context)` return byte-identical
    output (asserted in `test_fake_adapter.py`).
    """

    backend = "fake"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def render(self, template_bytes: bytes, context: Mapping[str, Any]) -> bytes:
        template_sha256 = hashlib.sha256(template_bytes).hexdigest()
        context_keys = sorted(context.keys())
        self.calls.append({
            "template_sha256": template_sha256,
            "context_keys": context_keys,
        })

        doc = Document()
        doc.add_paragraph(
            f"FAKE-DOCX-RENDER template_sha256={template_sha256} "
            f"context_keys={context_keys}"
        )
        buf = io.BytesIO()
        doc.save(buf)
        return buf.getvalue()

    def list_placeholders(self, template_bytes: bytes) -> set[str]:
        found: set[str] = set()
        loop_bound: set[str] = set()
        with zipfile.ZipFile(io.BytesIO(template_bytes)) as zf:
            xml_parts = [
                name for name in zf.namelist()
                if name.startswith("word/") and name.endswith(".xml")
            ]
            for name in xml_parts:
                xml = zf.read(name).decode("utf-8", errors="ignore")
                found.update(_VAR_RE.findall(xml))
                found.update(_IF_RE.findall(xml))
                for bound, iterable in _FOR_RE.findall(xml):
                    found.add(iterable)
                    loop_bound.update(v.strip() for v in bound.split(","))
        # Loop targets (`p` in `{% for p in parcelas %}`) are not context
        # keys — the Real adapter's `find_undeclared_variables` never reports
        # them, and a Fake that did would make a completeness gate under test
        # demand a key production never needs.
        return found - loop_bound
