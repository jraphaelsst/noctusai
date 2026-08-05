"""Hierarchical tool registry for the Omie MCP server.

Each leaf module exports the uniform `HANDLERS` / `tool_descriptors()` /
`register(server)` contract; `_kit.registry.build_registry` aggregates
them (shared across every connector MCP).

Tool naming follows the dotted convention `omie.<service>.<action>`.

**Tool profile.** Omie is a very large API, and the curated per-resource
CRUD tools are ~89 descriptors on their own. `OMIE_TOOL_PROFILE=core`
advertises only the always-needed 12 (environments · catalog · call ·
diagnostics) for hosts on a tight context budget. Capability is
unchanged — `omie.call.invoke` still reaches all 461 methods, and the
curated HANDLERS stay registered either way, so a host that already knows
a curated tool name can still call it. Only what is *advertised* shrinks.
"""
from __future__ import annotations

from _kit.registry import build_registry

from . import call, catalog_tools, diagnostics, environments, resources

LEAF_MODULES = (environments, catalog_tools, call, resources, diagnostics)

#: Advertised in every profile — these are how an agent orients, discovers
#: the API surface, and reaches any method.
CORE_MODULES = (environments, catalog_tools, call, diagnostics)

_all_handlers, _all_descriptors, register_all = build_registry(LEAF_MODULES)
_core_handlers, _core_descriptors, _ = build_registry(CORE_MODULES)


def all_handlers() -> dict:
    """Every handler, in every profile — a narrowed profile must not break
    a call the host already knows how to make."""
    return _all_handlers()


def all_descriptors() -> list:
    """Descriptors for the configured profile (`full` by default)."""
    from ..settings import get_settings

    try:
        profile = get_settings().tool_profile
    except Exception:  # noqa: BLE001 — a bad profile must not stop the server
        profile = "full"  # reported by omie.diagnostics.connection_status
    return _core_descriptors() if profile == "core" else _all_descriptors()


__all__ = [
    "LEAF_MODULES", "CORE_MODULES",
    "all_handlers", "all_descriptors", "register_all",
]
