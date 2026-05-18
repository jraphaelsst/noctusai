"""Connector-MCP shared error envelope.

Generalized from vista's per-tool `_typed_error` (`KB § INTEGRATIONS/vista.md
§ 3.4`). Every connector MCP renders an exception raised inside a tool
handler as a JSON-friendly dict with a stable shape so the host LLM can
branch on `error_class` / `status` deterministically.

Shape (frozen contract — connectors depend on these exact keys):
    {"error_class": <type name>, "message": <str(e)>, "status": <int|None>}

`status` is read off the exception via `getattr(e, "status", None)` — vendor
HTTP-error classes (VistaUpstreamError, the future Meta/Google equivalents)
carry the upstream status code there; plain exceptions yield None.
"""
from __future__ import annotations


def typed_error(e: Exception) -> dict:
    """Render any exception as the connector-MCP typed-error payload.

    Verbatim-equivalent to vista's `_typed_error` — same three keys, same
    `getattr(e, "status", None)` probe — so swapping vista's private copies
    for this is a zero-behavior-change refactor.
    """
    return {
        "error_class": type(e).__name__,
        "message": str(e),
        "status": getattr(e, "status", None),
    }


__all__ = ["typed_error"]
