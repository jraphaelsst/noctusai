"""Shared plumbing for the Omie tool modules.

Every Omie tool takes `environment` (see `settings.py` — an Omie
"environment" is a company, each with its own credential pair), and every
tool renders failures through the connector-MCP typed-error envelope
rather than raising across the MCP boundary. Both concerns live here so
no leaf module re-implements them.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from _kit.errors import typed_error

from ..errors import OmieApiError

#: Reusable JSON-schema fragment — every tool advertises `environment`.
ENV_PROPERTY = {
    "environment": {
        "type": "string",
        "description": (
            "Omie environment (company) to act on. Omit to use the configured "
            "default. Use omie.environments.list to see the options — an Omie "
            "'environment' is a company with its own app_key/app_secret."
        ),
    }
}

CONFIRM_PROPERTY = {
    "confirm": {
        "type": "boolean",
        "default": False,
        "description": (
            "Must be true to actually perform this write. Omie has no undo "
            "and no sandbox, so the call is refused (with no side-effect) "
            "until you confirm."
        ),
    }
}


def schema(properties: dict, required: list[str] | None = None, *, env: bool = True,
           confirm: bool = False) -> dict:
    """Build a tool inputSchema with the standard `environment`/`confirm` args."""
    props = {**(ENV_PROPERTY if env else {}), **(CONFIRM_PROPERTY if confirm else {}), **properties}
    out: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        out["required"] = required
    return out


async def guarded(fn: Callable[[], Awaitable[Any]]) -> dict:
    """Run a handler body, rendering any Omie failure as a typed error.

    Only `OmieApiError` (and its subclasses) is translated — an unexpected
    bug still propagates rather than being silently dressed up as a normal
    API failure (no-silent-errors).
    """
    try:
        result = await fn()
    except OmieApiError as e:
        return {"ok": False, "error": typed_error(e)}
    return {"ok": True, **result} if isinstance(result, dict) else {"ok": True, "result": result}


__all__ = ["ENV_PROPERTY", "CONFIRM_PROPERTY", "schema", "guarded"]
