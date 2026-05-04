"""Memory tool — `read_memory` + `write_memory`.

Wraps :class:`dev_team.memory.MemoryStore`. The store handles per-scope
gating (project / self / <other>); this layer just exposes the agno-tool
shape and validates scope strings.
"""

from __future__ import annotations

from typing import Any, Callable

from dev_team.memory import MemoryStore


_VALID_SCOPES = {"project", "self"}


def _normalize_scope(scope: str) -> str:
    """Return the validated scope string. ``self`` and ``project`` always
    valid; an arbitrary agent-name scope (cross-read) is also accepted —
    enforcement of cross-read permission lives in the agent's allowlist."""
    if not scope or not isinstance(scope, str):
        raise ValueError(f"scope must be a non-empty string; got {scope!r}")
    return scope


def read_memory(scope: str, key: str, *, store: MemoryStore | None = None) -> Any:
    """Read a value from memory.

    Args:
        scope: ``project`` (shared), ``self`` (own craft), or another agent
            name when cross-read is permitted by the allowlist.
        key: The key to read.
        store: Optional pre-built MemoryStore (for tests / custom project).

    Returns:
        The stored value, or None if absent.
    """
    scope = _normalize_scope(scope)
    backing = store or MemoryStore()
    return backing.read(scope, key)


def write_memory(
    scope: str,
    key: str,
    value: Any,
    *,
    store: MemoryStore | None = None,
) -> None:
    """Write a value to memory under ``scope``.

    Args:
        scope: ``project`` or ``self`` (writes to other agents' memory are
            schema-violations and refused at the store layer).
        key: The key to write.
        value: JSON-serialisable payload.
        store: Optional pre-built MemoryStore.
    """
    scope = _normalize_scope(scope)
    backing = store or MemoryStore()
    backing.write(scope, key, value)


def build_read_memory_tool(*, store: MemoryStore | None = None, **kwargs) -> Callable:
    """Return an agno-compatible read-memory tool, optionally bound to a store."""
    if store is None:
        return read_memory

    def _read(scope: str, key: str) -> Any:
        return read_memory(scope, key, store=store)

    _read.__name__ = "read_memory"
    _read.__doc__ = read_memory.__doc__
    return _read


def build_write_memory_tool(*, store: MemoryStore | None = None, **kwargs) -> Callable:
    """Return an agno-compatible write-memory tool, optionally bound to a store."""
    if store is None:
        return write_memory

    def _write(scope: str, key: str, value: Any) -> None:
        write_memory(scope, key, value, store=store)

    _write.__name__ = "write_memory"
    _write.__doc__ = write_memory.__doc__
    return _write


__all__ = [
    "read_memory",
    "write_memory",
    "build_read_memory_tool",
    "build_write_memory_tool",
]
