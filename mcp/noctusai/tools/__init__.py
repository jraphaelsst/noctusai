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
    from . import google, llm, noctus

    google.register_all(server)
    llm.register_all(server)
    noctus.register_all(server)


__all__ = ["register_all"]
