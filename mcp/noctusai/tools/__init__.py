"""MCP tool registration tree.

Each tool module exposes a ``register(server)`` function that calls
``server.tool(name=..., description=...)(handler)`` for every tool it
owns. Registration delegates to per-umbrella ``register_all``:

    tools/__init__.py::register_all
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
    from . import noctus

    noctus.register_all(server)


__all__ = ["register_all"]
