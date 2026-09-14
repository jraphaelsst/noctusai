"""Academia de Reciclagem — sibling-content importer (slice A2).

Turns a JSONL knowledge bundle (see ``bundle.py`` for the line shape)
into ``KnowledgeStore`` (§A.11 of ``projects/julia-agents-academia-CONTRACT.md``)
writes: one ``import_entity`` call per mapped entity, inside a single
transaction, idempotent on ``(git_sha, natural_key)``.

Modules:
  - ``secrets.py`` — content secret scan (known token patterns +
    Shannon-entropy heuristic). Shared, in spirit, with the export tool
    at ``mcp/noctusai/tools/noctus/dev/knowledge_bundle_export.py`` — see
    that module's docstring for why the logic is duplicated rather than
    imported across the product/mcp-toolkit boundary.
  - ``bundle.py`` — JSONL parsing, shape validation, size cap, and the
    path denylist.
  - ``mapping.py`` — pure per-path-shape mapping functions (§B.6).
  - ``run.py`` — the transactional orchestrator, ``run_import()``.

``app/knowledge/`` (A1, the ``KnowledgeStore`` implementation) does not
exist on this branch yet — A1 builds it in parallel off the same
contract. This package types against §A.11 behind ``TYPE_CHECKING`` and
duck-types at runtime; see ``run.py`` and
``tests/importer/_fake_store.py`` for the integration note.
"""
from __future__ import annotations
