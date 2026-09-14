"""Content secret scan for the knowledge-bundle importer (contract §B.6).

A1c hoisted the actual detector to
``noctusai_lib.security.secrets_scan`` (shared with
``mcp/noctusai/tools/noctus/dev/knowledge_bundle_export.py``, which had
an independent — but behaviourally identical — copy). This module is
now a thin re-export kept for the existing ``from app.importer.secrets
import scan_content`` call sites (``bundle.py``, this package's own
tests) and to keep the docstring's contract-facing framing local to the
importer.

Returns booleans only — **never** the value that matched, so a scan
result is always safe to log or return to a caller (contract: "returns
the offending path, never the value"). ``noctusai_lib.security.
find_secret`` additionally exposes the matched pattern NAME for callers
that want it.
"""
from __future__ import annotations

from noctusai_lib.security import has_secret

scan_content = has_secret

__all__ = ["scan_content"]
