"""Shared plumbing for every `vista.*` tool module.

Lifted 2026-09-16 at N=6: `_client()` had been copied into six leaf modules
and `_typed_error()` into five; the write tools would have been the seventh.
"""
from __future__ import annotations

from noctusai_lib.integrations.vista import VistaClient

from ..settings import get_settings


def client() -> VistaClient:
    """A `VistaClient` built from this process's per-tenant settings."""
    s = get_settings()
    return VistaClient(s.base_url, s.api_key, timeout_seconds=s.timeout_seconds)


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


class WritesDisabled(Exception):
    """The write tools refuse unless `VISTA_MCP_ALLOW_WRITES` opts in."""


def require_writes_enabled() -> None:
    if not get_settings().writes_enabled:
        raise WritesDisabled(
            "Vista write tools are disabled in this MCP process — they mutate "
            "the agency's live CRM. Set VISTA_MCP_ALLOW_WRITES=1 to enable."
        )


__all__ = ["client", "typed_error", "WritesDisabled", "require_writes_enabled"]
