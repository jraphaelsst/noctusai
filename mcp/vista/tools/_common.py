"""Shared plumbing for every `vista.*` tool module.

Lifted 2026-09-16 at N=6: `_client()` had been copied into six leaf modules
and `_typed_error()` into five; the write tools would have been the seventh.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from noctusai_lib.integrations.vista import (
    VistaClient,
    VistaConfigError,
    VistaFieldNotAvailable,
    VistaNotFound,
    VistaPermissionDenied,
    VistaTimeout,
    VistaUpstreamError,
    extract_relation,
)

from ..settings import get_settings

#: DI seam (KB § PATTERNS/backend/di-test-seam.md): `None` → build the Real
#: client from settings; tests install a factory returning a
#: `FakeVistaClient` instead of patching our own code.
_client_factory: Optional[Callable[[], Any]] = None


def configure_client_factory(factory: Optional[Callable[[], Any]]) -> None:
    """Install (or, with `None`, clear) the client factory every tool uses."""
    global _client_factory
    _client_factory = factory


def client() -> VistaClient:
    """The client every tool calls — the configured factory's, else a
    `VistaClient` built from this process's per-tenant settings."""
    if _client_factory is not None:
        return _client_factory()
    s = get_settings()
    return VistaClient(s.base_url, s.api_key, timeout_seconds=s.timeout_seconds)


#: Errors that mean "we could not read this" — surfaced as a typed_error,
#: never raised: an MCP tool that throws gives the host LLM nothing
#: actionable, while a typed 401 tells it exactly who to ask. Lifted here at
#: N=3 (clientes, corretores, and the 2026-10-27 read families).
HANDLED_READ_ERRORS: tuple[type[Exception], ...] = (
    VistaConfigError,
    VistaPermissionDenied,
    VistaNotFound,
    VistaFieldNotAvailable,
    VistaTimeout,
    VistaUpstreamError,
)


def probe_status_for(e: Exception) -> str:
    """Map a typed error back to the endpoint vocabulary the catalog uses."""
    if isinstance(e, VistaPermissionDenied):
        return "permission_gated"
    if isinstance(e, VistaNotFound):
        return "absent"
    return "live_probed"


def typed_error(e: Exception) -> dict:
    """Render a typed Vista error as a JSON-friendly payload (vista.md § 3).

    `str(e)` is safe to surface: the client redacts the API key at its HTTP
    boundary before any upstream text reaches an exception.
    """
    return {
        "error_class": type(e).__name__,
        "message": str(e),
        "status": getattr(e, "status", None),
    }


def history_page(payload: Any, relation: str, offset: int, limit: int) -> tuple[list[dict], int]:
    """Window a history relation (`prontuarios` / `historicos`) client-side.

    Vista answers the WHOLE relation in one body (333 entries for CA2830), so
    paging can only happen here. Returns `(window, total)`.
    """
    entries = extract_relation(payload, relation)
    return entries[offset : offset + limit], len(entries)


class WritesDisabled(Exception):
    """The write tools refuse unless `VISTA_MCP_ALLOW_WRITES` opts in."""


def require_writes_enabled() -> None:
    if not get_settings().writes_enabled:
        raise WritesDisabled(
            "Vista write tools are disabled in this MCP process — they mutate "
            "the agency's live CRM. Set VISTA_MCP_ALLOW_WRITES=1 to enable."
        )


__all__ = [
    "client",
    "configure_client_factory",
    "typed_error",
    "HANDLED_READ_ERRORS",
    "probe_status_for",
    "history_page",
    "WritesDisabled",
    "require_writes_enabled",
]
