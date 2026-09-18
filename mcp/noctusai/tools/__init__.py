"""MCP tool registration tree.

Each tool module exposes a ``register(server)`` function that calls
``server.tool(name=..., description=...)(handler)`` for every tool it
owns. Registration delegates to per-umbrella ``register_all``:

    tools/__init__.py::register_all
        -> tools/google/__init__.py::register_all
            -> tools/google/calendar/__init__.py::register_all
            -> tools/google/maps/__init__.py::register_all
        -> tools/llm/__init__.py::register_all
            -> tools/llm/audio/__init__.py::register_all
            -> tools/llm/vision/__init__.py::register_all
        -> tools/noctus/__init__.py::register_all
            -> tools/noctus/dev/__init__.py::register_all
                -> <24 tool modules>.register

Lazy-loading discipline: each umbrella imports its children inside
``register_all`` so the server's import-time stays light. Heavy deps in
tool modules (e.g. ``ai_brain`` pulls in OpenAI when invoked) only fire
when the registrar runs.
"""

from __future__ import annotations


def register_all(server) -> None:
    """Register every tool on the given FastMCP server."""
    from . import google, kb_sync, llm, noctus

    google.register_all(server)
    llm.register_all(server)
    noctus.register_all(server)
    # kb_sync lives at tools/kb_sync.py (not in an umbrella package) — it is
    # the absorbed scripts/verify-kb-sync.sh + scripts/update-kb-counts.py;
    # register it explicitly so noctus.dev.kb_sync is MCP-exposed.
    kb_sync.register(server)

    # 🔴 toolkit-staleness baseline (2026-09-18) — MUST be the LAST thing
    # register_all does: every umbrella above has now finished importing
    # its tool modules, so sys.modules holds the full mcp/noctusai module
    # graph this process will ever answer with. Freezing {path: (mtime,
    # size)} here — not lazily on first tool call — is what lets a LATER
    # on-disk edit be detected as drift instead of silently becoming the
    # new "fresh" baseline. See tools/noctus/dev/toolkit_freshness.py.
    from .noctus.dev import toolkit_freshness

    toolkit_freshness.capture_baseline()


__all__ = ["register_all"]
