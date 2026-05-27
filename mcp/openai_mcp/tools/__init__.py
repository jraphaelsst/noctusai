"""Hierarchical tool registry for the OpenAI connector MCP server.

Mirrors github/tools/__init__.py: each leaf module exports HANDLERS +
tool_descriptors() + register(server); build_registry assembles the trio.
"""
from __future__ import annotations

from _kit.registry import build_registry

from . import chat, diagnostics, embed, search, transcribe, vision

LEAF_MODULES = (diagnostics, embed, chat, vision, transcribe, search)

all_handlers, all_descriptors, register_all = build_registry(LEAF_MODULES)


__all__ = ["LEAF_MODULES", "all_handlers", "all_descriptors", "register_all"]
